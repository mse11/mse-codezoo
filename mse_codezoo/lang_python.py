"""Python adapter: CPython's ``ast`` -> IR, and IR -> Python text with a source map.

Parsing uses the real Python parser, so the syntax rules are CPython's own.
Anything outside the supported subset becomes a ``RawCode`` node: kept, never dropped.
Standard library only.
"""

from __future__ import annotations

import ast
import io
import math
import textwrap
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass, field

from mse_codezoo import ir
from mse_codezoo.i18n import t

BASELINE = (3, 11)
INDENT = "    "

BIN_OPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
    ast.BitOr: "|",
    ast.BitAnd: "&",
    ast.BitXor: "^",
}
UNARY_OPS: dict[type[ast.unaryop], str] = {ast.USub: "-", ast.UAdd: "+", ast.Not: "not"}
CMP_OPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
}
BOOL_OPS: dict[type[ast.boolop], str] = {ast.And: "and", ast.Or: "or"}
CONVERSIONS = {ord("r"): "r", ord("s"): "s", ord("a"): "a"}

# Python's operator precedence, weakest first (only the levels CodeZoo uses)
LAMBDA_PRECEDENCE = 0  # also `yield`, which needs brackets almost everywhere
IFEXP_PRECEDENCE = 1
BOOL_PRECEDENCE = {"or": 2, "and": 3}
NOT_PRECEDENCE = 4
CMP_PRECEDENCE = 5
PRECEDENCE = {
    "|": 7,
    "^": 8,
    "&": 9,
    "+": 10,
    "-": 10,
    "*": 11,
    "/": 11,
    "//": 11,
    "%": 11,
    "**": 13,
}
UNARY_PRECEDENCE = 12
POW_PRECEDENCE = 13
AWAIT_PRECEDENCE = 14
ATOM_PRECEDENCE = 15

FRIENDLY = {
    # statements
    "FunctionDef": "functions (`def`)",
    "AsyncFunctionDef": "async functions",
    "ClassDef": "classes",
    "Return": "`return`",
    "Import": "imports",
    "ImportFrom": "imports",
    "Try": "`try` blocks",
    "TryStar": "`try` blocks",
    "With": "`with` blocks",
    "Break": "`break`",
    "Continue": "`continue`",
    "Match": "`match` statements",
    "Delete": "`del`",
    "Global": "`global`",
    "Nonlocal": "`nonlocal`",
    "Raise": "`raise`",
    "Assert": "`assert`",
    "AnnAssign": "type hints",
    "AsyncWith": "async `with` blocks",
    "TypeAlias": "`type` aliases",
    # expressions
    "List": "lists",
    "Tuple": "tuples",
    "Dict": "dictionaries",
    "Set": "sets",
    "Attribute": "dots like `a.b`",
    "Subscript": "indexing like `a[0]`",
    "TemplateStr": 'template strings (`t"..."`)',
    "Interpolation": 'template strings (`t"..."`)',
    "Lambda": "`lambda`",
    "ListComp": "comprehensions",
    "SetComp": "comprehensions",
    "DictComp": "comprehensions",
    "GeneratorExp": "comprehensions",
    "Await": "`await`",
    "Starred": "`*` unpacking",
}


@dataclass(frozen=True)
class Span:
    line: int
    col: int
    end_line: int
    end_col: int


@dataclass
class Diagnostic:
    line: int
    col: int
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ParseResult:
    program: ir.Program | None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    positions: dict[str, Span] = field(default_factory=dict)  # node id -> span in the input

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def ok(self) -> bool:
        return self.program is not None and not self.errors


@dataclass
class PrintResult:
    text: str
    source_map: dict[str, Span]  # statement id -> span in ``text``


class Unsupported(Exception):
    """A construct outside the supported subset; the message names it kindly."""


def friendly_name(node: ast.AST) -> str:
    name = type(node).__name__
    return FRIENDLY.get(name, f"`{name}`")


# --- parsing -----------------------------------------------------------------


def parse(text: str, version: tuple[int, int] | None = None, *, id_prefix: str = "") -> ParseResult:
    """Parse Python ``text`` into IR, accepting only syntax available in ``version``
    (by default, the newest release this computer's Python can read).

    ``id_prefix`` keeps node ids of a helper file apart from the main program's.
    """
    from mse_codezoo import versions

    version = version or versions.DEFAULT
    try:
        try:
            tree = ast.parse(text, feature_version=min(version, versions.HOST))
        except SyntaxError:
            # newer syntax than `version`? Read it with everything this Python knows, so the
            # message can name the release that brought it
            tree = ast.parse(text, feature_version=versions.HOST)
            if not [n for n in versions.newer_syntax(tree, text) if n.since > version]:
                raise
    except SyntaxError as exc:
        line = exc.lineno or 1
        message = t("Python can't read line {line}: {why}.", line=line, why=exc.msg)
        hint = versions.host_hint(text)
        if hint is not None:
            message += " " + t(
                "{what} need Python {since}, but this computer runs Python {host}.",
                what=t(hint[0]),
                since=versions.version_text(hint[1]),
                host=versions.version_text(versions.HOST),
            )
        return ParseResult(None, [Diagnostic(line, max((exc.offset or 1) - 1, 0), message)])
    except ValueError as exc:  # e.g. null bytes in the source
        return ParseResult(
            None, [Diagnostic(1, 0, t("Python can't read this file: {why}.", why=exc))]
        )
    too_new = [n for n in versions.newer_syntax(tree, text) if n.since > version]
    if too_new:
        return ParseResult(
            None,
            [
                Diagnostic(
                    n.line,
                    n.col,
                    t(
                        "{what} arrived in Python {since}; this program is set to Python {now}.",
                        what=t(n.what),
                        since=versions.version_text(n.since),
                        now=versions.version_text(version),
                    ),
                )
                for n in too_new
            ],
        )
    converter = _Converter(text, id_prefix)
    program = converter.program(tree)
    return ParseResult(program, converter.diagnostics, converter.positions)


def _scan_comments(text: str) -> tuple[list[tuple[int, int, str]], dict[int, str]]:
    """Full-line comments as (line, col, text) and inline comments by line."""
    full: list[tuple[int, int, str]] = []
    inline: dict[int, str] = {}
    lines = text.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return full, inline
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line, col = token.start
        body = token.string[1:]
        if body.startswith(" "):
            body = body[1:]
        if lines[line - 1][:col].strip():
            inline[line] = body
        else:
            full.append((line, col, body))
    return full, inline


class _Converter:
    def __init__(self, text: str, id_prefix: str = "") -> None:
        self.lines = text.splitlines()
        self.new_id = ir.Ids(f"{id_prefix}n")
        self.diagnostics: list[Diagnostic] = []
        self.positions: dict[str, Span] = {}
        self.comments, self.inline = _scan_comments(text)

    def program(self, tree: ast.Module) -> ir.Program:
        program_id = self.new_id()
        return ir.Program(id=program_id, body=self.body(tree.body, indent=0, stop_line=math.inf))

    def body(self, stmts: list[ast.stmt], indent: int, stop_line: float) -> list[ir.Stmt]:
        out: list[ir.Stmt] = []
        for i, node in enumerate(stmts):
            out += self.take_comments(before=first_line(node))
            next_line = first_line(stmts[i + 1]) if i + 1 < len(stmts) else stop_line
            out.append(self.stmt(node, next_line))
        out += self.take_comments(before=stop_line, min_col=indent)
        return out

    def take_comments(self, before: float, min_col: int = 0) -> list[ir.Stmt]:
        taken: list[ir.Stmt] = []
        while self.comments and self.comments[0][0] < before and self.comments[0][1] >= min_col:
            line, col, text = self.comments.pop(0)
            comment = ir.Comment(id=self.new_id(), text=text)
            self.positions[comment.id] = Span(line, col, line, len(self.lines[line - 1]))
            taken.append(comment)
        return taken

    def span(self, node: ast.AST) -> Span:
        return Span(
            node.lineno,
            node.col_offset,
            node.end_lineno or node.lineno,
            node.end_col_offset or 0,
        )

    def stmt(self, node: ast.stmt, next_line: float) -> ir.Stmt:
        stmt_id = self.new_id()
        start = first_line(node)
        span = self.span(node)
        self.positions[stmt_id] = Span(start, span.col, span.end_line, span.end_col)
        try:
            result = self._stmt(node, stmt_id, next_line)
        except Unsupported as exc:
            end = node.end_lineno or node.lineno
            # inner comments are part of the raw text; don't emit them twice
            self.comments = [c for c in self.comments if c[0] > end]
            text = textwrap.dedent("\n".join(self.lines[start - 1 : end]))
            reason = str(exc)
            self.diagnostics.append(
                Diagnostic(
                    node.lineno,
                    node.col_offset,
                    t(
                        "CodeZoo can't turn {what} into blocks yet; kept as raw code.",
                        what=t(reason),
                    ),
                    "warning",
                )
            )
            return ir.RawCode(id=stmt_id, text=text, reason=reason)
        result.comment = self.inline.get(node.lineno)
        return result

    def _stmt(self, node: ast.stmt, stmt_id: str, next_line: float) -> ir.Stmt:
        match node:
            case ast.Expr(value=value):
                return ir.ExprStmt(id=stmt_id, value=self.expr(value))
            case ast.Assign(targets=[target], value=value):
                return ir.Assign(id=stmt_id, target=self.target(target), value=self.expr(value))
            case ast.Assign():
                raise Unsupported("`a = b = ...` with several `=`")
            case ast.AnnAssign(target=ast.Name() | ast.Attribute() as target, annotation=ann):
                return ir.AnnAssign(
                    id=stmt_id,
                    target=self.target(target),
                    annotation=self.expr(ann),
                    value=None if node.value is None else self.expr(node.value),
                )
            case ast.AugAssign(
                target=ast.Name() | ast.Subscript() | ast.Attribute() as target, op=op, value=value
            ) if type(op) in BIN_OPS:
                return ir.AugAssign(
                    id=stmt_id,
                    target=self.target(target),
                    op=BIN_OPS[type(op)],
                    value=self.expr(value),
                )
            case (
                ast.For(target=target, iter=iterable, body=body, orelse=[])
                | ast.AsyncFor(target=target, iter=iterable, body=body, orelse=[])
            ):
                header_target = self.loop_target(target)
                header_iter = self.expr(iterable)
                return ir.For(
                    id=stmt_id,
                    target=header_target,
                    iter=header_iter,
                    body=self.body(body, indent=body[0].col_offset, stop_line=next_line),
                    is_async=isinstance(node, ast.AsyncFor),
                )
            case ast.If(test=test, body=body, orelse=orelse):
                header_test = self.expr(test)
                else_line = self._else_line(node) if orelse else next_line
                return ir.If(
                    id=stmt_id,
                    test=header_test,
                    body=self.body(body, indent=body[0].col_offset, stop_line=else_line),
                    orelse=self._orelse(orelse, else_line, next_line),
                )
            case ast.While(test=test, body=body, orelse=[]):
                header_test = self.expr(test)
                return ir.While(
                    id=stmt_id,
                    test=header_test,
                    body=self.body(body, indent=body[0].col_offset, stop_line=next_line),
                )
            case ast.FunctionDef() | ast.AsyncFunctionDef():
                return self.function(node, stmt_id, next_line)
            case ast.ClassDef():
                return self.class_(node, stmt_id, next_line)
            case ast.With(items=items, body=body) | ast.AsyncWith(items=items, body=body):
                with_items = [
                    ir.WithItem(
                        id=self.new_id(),
                        context=self.expr(item.context_expr),
                        target=None
                        if item.optional_vars is None
                        else self.target(item.optional_vars),
                    )
                    for item in items
                ]
                return ir.With(
                    id=stmt_id,
                    items=with_items,
                    body=self.body(body, indent=body[0].col_offset, stop_line=next_line),
                    is_async=isinstance(node, ast.AsyncWith),
                )
            case ast.Nonlocal(names=names):
                return ir.Nonlocal(id=stmt_id, names=list(names))
            case ast.Match():
                return self.match_(node, stmt_id, next_line)
            case _ if type(node).__name__ == "TypeAlias":
                return ir.TypeAlias(
                    id=stmt_id,
                    name=node.name.id,  # type: ignore[attr-defined]
                    type_params=self.type_params(node),
                    value=self.expr(node.value),  # type: ignore[attr-defined]
                )
            case ast.Return(value=value):
                return ir.Return(id=stmt_id, value=None if value is None else self.expr(value))
            case ast.Break():
                return ir.Break(id=stmt_id)
            case ast.Continue():
                return ir.Continue(id=stmt_id)
            case ast.Global(names=names):
                return ir.Global(id=stmt_id, names=list(names))
            case ast.Try() | ast.TryStar():
                return self.try_(node, stmt_id, next_line)
            case ast.Raise(exc=exc, cause=None):
                return ir.Raise(id=stmt_id, exc=None if exc is None else self.expr(exc))
            case ast.Raise():
                raise Unsupported("`raise ... from`")
            case ast.Assert(test=test, msg=msg):
                return ir.Assert(
                    id=stmt_id, test=self.expr(test), msg=None if msg is None else self.expr(msg)
                )
            case ast.Delete(targets=targets):
                return ir.Delete(id=stmt_id, targets=[self.target(t) for t in targets])
            case ast.Import(names=[ast.alias(name=module, asname=None)]) if "." not in module:
                return ir.Import(id=stmt_id, module=module, lazy=_is_lazy(node))
            case ast.ImportFrom(module=str() as module, names=names, level=0) if (
                "." not in module and all(a.asname is None and a.name != "*" for a in names)
            ):
                return ir.Import(
                    id=stmt_id, module=module, names=[a.name for a in names], lazy=_is_lazy(node)
                )
            case ast.Pass():
                return ir.Pass(id=stmt_id)
        raise Unsupported(friendly_name(node))

    def function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, stmt_id: str, next_line: float
    ) -> ir.FunctionDef:
        decorators = [self.expr(d) for d in node.decorator_list]
        type_params = self.type_params(node)
        params = self.params(node.args)
        returns = None if node.returns is None else self.expr(node.returns)
        body = node.body
        return ir.FunctionDef(
            id=stmt_id,
            name=node.name,
            params=params,
            body=self.body(body, indent=body[0].col_offset, stop_line=next_line),
            decorators=decorators,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            returns=returns,
            type_params=type_params,
        )

    def params(self, args: ast.arguments) -> list[ir.Param]:
        if args.posonlyargs:
            raise Unsupported("`/` in a function's inputs")
        defaults: list[ast.expr | None] = [None] * (len(args.args) - len(args.defaults))
        defaults += list(args.defaults)
        out = [
            self.param(arg, default, "plain")
            for arg, default in zip(args.args, defaults, strict=True)
        ]
        if args.vararg is not None:
            out.append(self.param(args.vararg, None, "args"))
        for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            out.append(self.param(arg, default, "kwonly"))
        if args.kwarg is not None:
            out.append(self.param(args.kwarg, None, "kwargs"))
        return out

    def param(self, arg: ast.arg, default: ast.expr | None, kind: str) -> ir.Param:
        return ir.Param(
            id=self.new_id(),
            name=arg.arg,
            default=None if default is None else self.expr(default),
            kind=kind,
            annotation=None if arg.annotation is None else self.expr(arg.annotation),
        )

    def type_params(self, node: ast.AST) -> list[str]:
        names = []
        for param in getattr(node, "type_params", None) or []:
            if type(param).__name__ != "TypeVar" or param.bound is not None:
                raise Unsupported("type parameters")
            if getattr(param, "default_value", None) is not None:
                raise Unsupported("type parameters")
            names.append(param.name)
        return names

    def class_(self, node: ast.ClassDef, stmt_id: str, next_line: float) -> ir.ClassDef:
        decorators = [self.expr(d) for d in node.decorator_list]
        type_params = self.type_params(node)
        if any(k.arg is None for k in node.keywords):
            raise Unsupported("`**` unpacking")
        bases = [self.expr(b) for b in node.bases]
        keywords = [self.keyword(k) for k in node.keywords]
        body = node.body
        return ir.ClassDef(
            id=stmt_id,
            name=node.name,
            bases=bases,
            keywords=keywords,
            body=self.body(body, indent=body[0].col_offset, stop_line=next_line),
            decorators=decorators,
            type_params=type_params,
        )

    def match_(self, node: ast.Match, stmt_id: str, next_line: float) -> ir.Match:
        subject = self.expr(node.subject)
        starts: list[float] = [c.pattern.lineno for c in node.cases] + [next_line]
        cases = []
        for number, case in enumerate(node.cases):
            case_id = self.new_id()
            line = case.pattern.lineno
            self.positions[case_id] = Span(line, 0, line, len(self.lines[line - 1]))
            pattern = self.pattern(case.pattern)
            guard = None if case.guard is None else self.expr(case.guard)
            inner = self.body(
                case.body, indent=case.body[0].col_offset, stop_line=starts[number + 1]
            )
            cases.append(ir.MatchCase(id=case_id, pattern=pattern, guard=guard, body=inner))
        return ir.Match(id=stmt_id, subject=subject, cases=cases)

    def pattern(self, node: ast.pattern) -> ir.Pattern:
        pattern_id = self.new_id()
        match node:
            case ast.MatchValue(value=value):
                return ir.PatternValue(id=pattern_id, value=self.expr(value))
            case ast.MatchSingleton(value=value):
                return ir.PatternValue(id=pattern_id, value=ir.Const(id=self.new_id(), value=value))
            case ast.MatchAs(pattern=None, name=name):
                return ir.PatternCapture(id=pattern_id, name=name)
            case ast.MatchAs(pattern=inner, name=str() as name):
                return ir.PatternAs(id=pattern_id, pattern=self.pattern(inner), name=name)
            case ast.MatchOr(patterns=patterns):
                return ir.PatternOr(id=pattern_id, patterns=[self.pattern(p) for p in patterns])
            case ast.MatchSequence(patterns=patterns):
                return ir.PatternSequence(
                    id=pattern_id, patterns=[self.pattern(p) for p in patterns]
                )
            case ast.MatchStar(name=name):
                return ir.PatternStar(id=pattern_id, name=name)
            case ast.MatchMapping(keys=keys, patterns=patterns, rest=rest):
                return ir.PatternMapping(
                    id=pattern_id,
                    keys=[self.expr(k) for k in keys],
                    patterns=[self.pattern(p) for p in patterns],
                    rest=rest,
                )
            case ast.MatchClass(cls=cls, patterns=patterns, kwd_attrs=names, kwd_patterns=kwds):
                return ir.PatternClass(
                    id=pattern_id,
                    cls=self.expr(cls),
                    patterns=[self.pattern(p) for p in patterns],
                    kwd_names=list(names),
                    kwd_patterns=[self.pattern(p) for p in kwds],
                )
        raise Unsupported("this kind of `case`")

    def try_(self, node: ast.Try | ast.TryStar, stmt_id: str, next_line: float) -> ir.Try:
        def header(keyword: str, section: list[ast.stmt], after: int) -> int:
            """The line of the `else:` / `finally:` that opens ``section``."""
            for line in range(section[0].lineno, after, -1):
                if self.lines[line - 1][node.col_offset :].startswith(keyword):
                    return line
            return section[0].lineno

        def end(stmts: list[ast.stmt]) -> int:
            return stmts[-1].end_lineno or stmts[-1].lineno

        starts: list[float] = [h.lineno for h in node.handlers]  # where each part begins
        after = end(node.handlers[-1].body) if node.handlers else end(node.body)
        else_line = finally_line = None
        if node.orelse:
            else_line = header("else", node.orelse, after)
            starts.append(else_line)
            after = end(node.orelse)
        if node.finalbody:
            finally_line = header("finally", node.finalbody, after)
            starts.append(finally_line)
        starts.append(next_line)

        body = self.body(node.body, indent=node.body[0].col_offset, stop_line=starts[0])
        handlers = []
        for number, handler in enumerate(node.handlers):
            handler_id = self.new_id()
            self.positions[handler_id] = Span(
                handler.lineno,
                handler.col_offset,
                handler.lineno,
                len(self.lines[handler.lineno - 1]),
            )
            kind = None if handler.type is None else self.except_kind(handler.type)
            note = self._header_note(handler.lineno, handler.body[0].lineno)
            inner = self.body(
                handler.body, indent=handler.body[0].col_offset, stop_line=starts[number + 1]
            )
            handlers.append(
                ir.ExceptHandler(id=handler_id, kind=kind, name=handler.name, body=note + inner)
            )
        rest = starts[len(node.handlers) :]
        orelse: list[ir.Stmt] = []
        finalbody: list[ir.Stmt] = []
        if else_line is not None:
            rest.pop(0)
            orelse = self._header_note(else_line, node.orelse[0].lineno) + self.body(
                node.orelse, indent=node.orelse[0].col_offset, stop_line=rest[0]
            )
        if finally_line is not None:
            rest.pop(0)
            finalbody = self._header_note(finally_line, node.finalbody[0].lineno) + self.body(
                node.finalbody, indent=node.finalbody[0].col_offset, stop_line=rest[0]
            )
        return ir.Try(
            id=stmt_id,
            body=body,
            handlers=handlers,
            orelse=orelse,
            finalbody=finalbody,
            star=isinstance(node, ast.TryStar),
        )

    def _header_note(self, line: float, first_line: int) -> list[ir.Stmt]:
        """A comment on an `except:` / `else:` / `finally:` line, kept as a note."""
        note = self.inline.get(int(line))
        if note is None or line == first_line:
            return []
        return [ir.Comment(id=self.new_id(), text=note)]

    def except_kind(self, node: ast.expr) -> ir.Expr:
        if isinstance(node, ast.Name):
            return self.expr(node)
        if isinstance(node, ast.Tuple) and all(isinstance(e, ast.Name) for e in node.elts):
            return self.expr(node)
        raise Unsupported("this kind of `except`")

    def target(self, node: ast.expr) -> ir.Expr:
        """The left side of `=`, `del` or a loop: names, `a[i]`, or a tuple of them."""
        match node:
            case ast.Name():
                return self.name(node)
            case ast.Subscript() | ast.Attribute():
                return self.expr(node)
            case ast.Tuple(elts=elts) | ast.List(elts=elts):
                tuple_id = self.new_id()
                self.positions[tuple_id] = self.span(node)
                if sum(isinstance(e, ast.Starred) for e in elts) > 1:
                    raise Unsupported("`*` unpacking")
                return ir.Tuple(id=tuple_id, elts=[self.target(e) for e in elts])
            case ast.Starred(value=ast.Name() as value):
                starred_id = self.new_id()
                self.positions[starred_id] = self.span(node)
                return ir.Starred(id=starred_id, value=self.name(value))
        raise Unsupported(friendly_name(node))

    def loop_target(self, node: ast.expr) -> ir.Expr:
        if isinstance(node, ast.Name):
            return self.name(node)
        if isinstance(node, ast.Tuple) and all(isinstance(e, ast.Name) for e in node.elts):
            return self.target(node)
        raise Unsupported("this kind of loop variable")

    def _else_line(self, node: ast.If) -> int:
        """The line of the ``else:`` or ``elif`` that ends the ``if`` body."""
        first = node.orelse[0]
        if isinstance(first, ast.If) and self.lines[first.lineno - 1][
            first.col_offset :
        ].startswith("elif"):
            return first.lineno
        last = node.body[-1].end_lineno or node.body[-1].lineno
        for line in range(first.lineno - 1, last, -1):
            if self.lines[line - 1].strip().startswith("else"):
                return line
        return first.lineno

    def _orelse(self, orelse: list[ast.stmt], else_line: float, next_line: float) -> list[ir.Stmt]:
        if not orelse:
            return []
        first = orelse[0]
        if len(orelse) == 1 and isinstance(first, ast.If) and first.lineno == else_line:
            return [self.stmt(first, next_line)]  # elif
        out: list[ir.Stmt] = []
        note = self.inline.get(int(else_line))
        if note is not None and else_line != first.lineno:
            out.append(ir.Comment(id=self.new_id(), text=note))  # keep a comment on `else:`
        return out + self.body(orelse, indent=first.col_offset, stop_line=next_line)

    def name(self, node: ast.Name) -> ir.Name:
        result = ir.Name(id=self.new_id(), name=node.id)
        self.positions[result.id] = self.span(node)
        return result

    def expr(self, node: ast.expr) -> ir.Expr:
        expr_id = self.new_id()
        self.positions[expr_id] = self.span(node)
        match node:
            case ast.Constant(value=value) if value is None or isinstance(
                value, bool | int | float | str
            ):
                return ir.Const(id=expr_id, value=value)
            case ast.Name(id=name):
                return ir.Name(id=expr_id, name=name)
            case ast.Call(func=ast.Name(id=func), args=args, keywords=keywords):
                return ir.Call(
                    id=expr_id,
                    func=func,
                    args=[self.element(a) for a in args],
                    keywords=[self.keyword(k) for k in keywords],
                )
            case ast.Call(func=ast.Attribute(value=obj, attr=method), args=args, keywords=keywords):
                return ir.MethodCall(
                    id=expr_id,
                    obj=self.expr(obj),
                    method=method,
                    args=[self.element(a) for a in args],
                    keywords=[self.keyword(k) for k in keywords],
                )
            case ast.Call():
                raise Unsupported("this kind of call")
            case ast.BinOp(left=left, op=op, right=right) if type(op) in BIN_OPS:
                return ir.BinOp(
                    id=expr_id, op=BIN_OPS[type(op)], left=self.expr(left), right=self.expr(right)
                )
            case ast.UnaryOp(op=op, operand=operand) if type(op) in UNARY_OPS:
                return ir.UnaryOp(id=expr_id, op=UNARY_OPS[type(op)], operand=self.expr(operand))
            case ast.Compare(left=left, ops=ops, comparators=comparators):
                return ir.Compare(
                    id=expr_id,
                    left=self.expr(left),
                    ops=[CMP_OPS[type(op)] for op in ops],
                    comparators=[self.expr(c) for c in comparators],
                )
            case ast.BoolOp(op=op, values=values):
                return ir.BoolOp(
                    id=expr_id, op=BOOL_OPS[type(op)], values=[self.expr(v) for v in values]
                )
            case ast.IfExp(test=test, body=body, orelse=orelse):
                return ir.IfExp(
                    id=expr_id,
                    test=self.expr(test),
                    body=self.expr(body),
                    orelse=self.expr(orelse),
                )
            case ast.JoinedStr(values=values):
                return ir.FString(id=expr_id, parts=[self.fstring_part(v) for v in values])
            case ast.Subscript(value=value, slice=index):
                return ir.Subscript(id=expr_id, value=self.expr(value), index=self.index(index))
            case ast.Attribute(value=value, attr=attr):
                return ir.Attribute(id=expr_id, value=self.expr(value), attr=attr)
            case ast.List(elts=elts):
                return ir.List(id=expr_id, elts=[self.element(e) for e in elts])
            case ast.Tuple(elts=elts):
                return ir.Tuple(id=expr_id, elts=[self.element(e) for e in elts])
            case ast.Set(elts=elts):
                return ir.Set(id=expr_id, elts=[self.element(e) for e in elts])
            case ast.Dict(keys=keys, values=values):
                return ir.Dict(
                    id=expr_id,
                    keys=[None if k is None else self.expr(k) for k in keys],
                    values=[self.expr(v) for v in values],
                )
            case ast.ListComp(elt=elt, generators=generators):
                return ir.Comprehension(
                    id=expr_id, kind="list", elt=self.element(elt), generators=self.comp(generators)
                )
            case ast.SetComp(elt=elt, generators=generators):
                return ir.Comprehension(
                    id=expr_id, kind="set", elt=self.element(elt), generators=self.comp(generators)
                )
            case ast.GeneratorExp(elt=elt, generators=generators):
                return ir.Comprehension(
                    id=expr_id,
                    kind="generator",
                    elt=self.element(elt),
                    generators=self.comp(generators),
                )
            case ast.Lambda(args=args, body=body):
                return ir.Lambda(id=expr_id, params=self.params(args), body=self.expr(body))
            case ast.Yield(value=value):
                return ir.Yield(id=expr_id, value=None if value is None else self.expr(value))
            case ast.YieldFrom(value=value):
                return ir.YieldFrom(id=expr_id, value=self.expr(value))
            case ast.Await(value=value):
                return ir.Await(id=expr_id, value=self.expr(value))
            case ast.NamedExpr(target=ast.Name(id=name), value=value):
                return ir.NamedExpr(
                    id=expr_id, target=ir.Name(id=f"{expr_id}.t", name=name), value=self.expr(value)
                )
            case _ if type(node).__name__ == "TemplateStr":
                return ir.TString(
                    id=expr_id,
                    parts=[self.fstring_part(v) for v in node.values],  # type: ignore[attr-defined]
                )
            case ast.DictComp(key=key, value=value, generators=generators):
                return ir.Comprehension(
                    id=expr_id,
                    kind="dict",
                    elt=self.expr(key),
                    value=self.expr(value),
                    generators=self.comp(generators),
                )
            case ast.Constant():
                raise Unsupported("this kind of value")
        raise Unsupported(friendly_name(node))

    def element(self, node: ast.expr) -> ir.Expr:
        """An item of a list, tuple or set literal; ``*others`` is allowed there."""
        if isinstance(node, ast.Starred):
            starred_id = self.new_id()
            self.positions[starred_id] = self.span(node)
            return ir.Starred(id=starred_id, value=self.expr(node.value))
        return self.expr(node)

    def comp(self, generators: list[ast.comprehension]) -> list[ir.CompFor]:
        out = []
        for gen in generators:
            if gen.is_async:
                raise Unsupported("async comprehensions")
            out.append(
                ir.CompFor(
                    id=self.new_id(),
                    target=self.loop_target(gen.target),
                    iter=self.expr(gen.iter),
                    ifs=[self.expr(i) for i in gen.ifs],
                )
            )
        return out

    def keyword(self, node: ast.keyword) -> ir.Keyword:
        return ir.Keyword(id=self.new_id(), name=node.arg, value=self.expr(node.value))

    def index(self, node: ast.expr) -> ir.Expr:
        if isinstance(node, ast.Slice):
            slice_id = self.new_id()
            self.positions[slice_id] = self.span(node)
            lower, upper, step = (
                None if part is None else self.expr(part)
                for part in (node.lower, node.upper, node.step)
            )
            return ir.Slice(id=slice_id, lower=lower, upper=upper, step=step)
        return self.expr(node)

    def fstring_part(self, node: ast.expr) -> ir.Expr:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return ir.Const(id=self.new_id(), value=node.value)
        if not isinstance(node, ast.FormattedValue) and type(node).__name__ != "Interpolation":
            raise Unsupported("this kind of f-string")
        spec = None
        if node.format_spec is not None:
            parts = getattr(node.format_spec, "values", [])
            if not all(isinstance(p, ast.Constant) and isinstance(p.value, str) for p in parts):
                raise Unsupported("f-string formats with `{}` inside")
            spec = "".join(p.value for p in parts)
        return ir.FormattedValue(
            id=self.new_id(),
            value=self.expr(node.value),
            conversion=CONVERSIONS.get(node.conversion),
            spec=spec,
        )


def first_line(node: ast.stmt) -> int:
    """Where a statement starts: its first decorator, if it has any."""
    decorators = getattr(node, "decorator_list", None) or []
    return min([node.lineno, *(d.lineno for d in decorators)])


def _is_lazy(node: ast.stmt) -> bool:
    return bool(getattr(node, "is_lazy", False))


# --- printing ----------------------------------------------------------------


def print_program(program: ir.Program) -> PrintResult:
    """Canonical Python text for ``program`` plus statement id -> span."""
    printer = _Printer()
    printer.body(program.body, depth=0)
    text = "\n".join(printer.lines) + ("\n" if printer.lines else "")
    return PrintResult(text, printer.source_map)


class _Printer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.source_map: dict[str, Span] = {}

    def body(self, stmts: list[ir.Stmt], depth: int) -> None:
        if not stmts and depth > 0:
            self.lines.append(INDENT * depth + "pass")
        for stmt in stmts:
            self.stmt(stmt, depth)

    def stmt(self, stmt: ir.Stmt, depth: int) -> None:
        pad = INDENT * depth
        start = len(self.lines) + 1
        match stmt:
            case ir.Comment(text=text):
                self.lines.append(pad + (f"# {text}" if text else "#"))
            case ir.RawCode(text=text):
                self.lines += [pad + line if line.strip() else "" for line in text.splitlines()]
            case ir.For(target=target, iter=iterable, body=body):
                keyword = "async for" if stmt.is_async else "for"
                head = f"{pad}{keyword} {target_to_text(target)} in {expr_to_text(iterable)}:"
                self.emit(head, stmt)
                self.body(body, depth + 1)
            case ir.FunctionDef(name=name, params=params, body=body):
                self.lines += [f"{pad}@{expr_to_text(d)}" for d in stmt.decorators]
                keyword = "async def" if stmt.is_async else "def"
                head = (
                    f"{pad}{keyword} {name}{_type_params(stmt.type_params)}({params_text(params)})"
                )
                if stmt.returns is not None:
                    head += f" -> {expr_to_text(stmt.returns)}"
                self.emit(head + ":", stmt)
                self.body(body, depth + 1)
            case ir.ClassDef(name=name, bases=bases, keywords=keywords, body=body):
                self.lines += [f"{pad}@{expr_to_text(d)}" for d in stmt.decorators]
                parts = [expr_to_text(b) for b in bases]
                parts += [f"{k.name}={expr_to_text(k.value)}" for k in keywords]
                inside = f"({', '.join(parts)})" if parts else ""
                self.emit(f"{pad}class {name}{_type_params(stmt.type_params)}{inside}:", stmt)
                self.body(body, depth + 1)
            case ir.With(items=items, body=body):
                keyword = "async with" if stmt.is_async else "with"
                parts = [
                    expr_to_text(item.context)
                    + ("" if item.target is None else f" as {target_to_text(item.target)}")
                    for item in items
                ]
                self.emit(f"{pad}{keyword} {', '.join(parts)}:", stmt)
                self.body(body, depth + 1)
            case ir.Match(subject=subject, cases=cases):
                self.emit(f"{pad}match {target_to_text(subject)}:", stmt)
                inner = INDENT * (depth + 1)
                for case in cases:
                    line = f"{inner}case {pattern_to_text(case.pattern, top=True)}"
                    if case.guard is not None:
                        line += f" if {expr_to_text(case.guard)}"
                    self.lines.append(line + ":")
                    row = len(self.lines)
                    self.source_map[case.id] = Span(row, len(inner), row, len(self.lines[-1]))
                    self.body(case.body, depth + 2)
            case ir.Try(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody):
                self.emit(f"{pad}try:", stmt)
                self.body(body, depth + 1)
                for handler in handlers:
                    line = f"{pad}except*" if stmt.star else f"{pad}except"
                    if handler.kind is not None:
                        line += " " + expr_to_text(handler.kind)
                    if handler.name is not None:
                        line += f" as {handler.name}"
                    self.lines.append(line + ":")
                    row = len(self.lines)
                    self.source_map[handler.id] = Span(row, len(pad), row, len(self.lines[-1]))
                    self.body(handler.body, depth + 1)
                if orelse:
                    self.lines.append(f"{pad}else:")
                    self.body(orelse, depth + 1)
                if finalbody:
                    self.lines.append(f"{pad}finally:")
                    self.body(finalbody, depth + 1)
            case ir.While(test=test, body=body):
                self.emit(f"{pad}while {expr_to_text(test)}:", stmt)
                self.body(body, depth + 1)
            case ir.If():
                self.if_chain(stmt, depth, "if")
            case _:
                self.emit(pad + _simple_stmt_text(stmt), stmt)
        end = len(self.lines)
        if end >= start:
            self.source_map[stmt.id] = Span(start, len(pad), end, len(self.lines[end - 1]))

    def if_chain(self, stmt: ir.If, depth: int, keyword: str) -> None:
        pad = INDENT * depth
        start = len(self.lines) + 1
        self.emit(f"{pad}{keyword} {expr_to_text(stmt.test)}:", stmt)
        self.body(stmt.body, depth + 1)
        orelse = stmt.orelse
        if len(orelse) == 1 and isinstance(orelse[0], ir.If):
            self.if_chain(orelse[0], depth, "elif")
        elif orelse:
            self.lines.append(f"{pad}else:")
            self.body(orelse, depth + 1)
        if keyword == "elif":  # an `if` gets its span from stmt()
            end = len(self.lines)
            self.source_map[stmt.id] = Span(start, len(pad), end, len(self.lines[end - 1]))

    def emit(self, line: str, stmt: ir.Stmt) -> None:
        if stmt.comment is not None:
            line += f"  # {stmt.comment}" if stmt.comment else "  #"
        self.lines.append(line)


def _simple_stmt_text(stmt: ir.Stmt) -> str:
    match stmt:
        case ir.ExprStmt(value=ir.NamedExpr() as value):
            return f"({expr_to_text(value)})"
        case ir.ExprStmt(value=value):
            return expr_to_text(value)
        case ir.Assign(target=target, value=ir.NamedExpr() as value):
            return f"{target_to_text(target)} = ({expr_to_text(value)})"
        case ir.Assign(target=target, value=value):
            return f"{target_to_text(target)} = {target_to_text(value)}"
        case ir.AnnAssign(target=target, annotation=annotation, value=None):
            return f"{expr_to_text(target)}: {expr_to_text(annotation)}"
        case ir.AnnAssign(target=target, annotation=annotation, value=value):
            return f"{expr_to_text(target)}: {expr_to_text(annotation)} = {target_to_text(value)}"
        case ir.Nonlocal(names=names):
            return f"nonlocal {', '.join(names)}"
        case ir.TypeAlias(name=name, type_params=type_params, value=value):
            return f"type {name}{_type_params(type_params)} = {expr_to_text(value)}"
        case ir.AugAssign(target=target, op=op, value=value):
            return f"{target_to_text(target)} {op}= {expr_to_text(value)}"
        case ir.Return(value=None):
            return "return"
        case ir.Return(value=value):
            return f"return {target_to_text(value)}"
        case ir.Break():
            return "break"
        case ir.Continue():
            return "continue"
        case ir.Global(names=names):
            return f"global {', '.join(names)}"
        case ir.Raise(exc=None):
            return "raise"
        case ir.Raise(exc=exc):
            return f"raise {expr_to_text(exc)}"
        case ir.Assert(test=test, msg=None):
            return f"assert {expr_to_text(test)}"
        case ir.Assert(test=test, msg=msg):
            return f"assert {expr_to_text(test)}, {expr_to_text(msg)}"
        case ir.Delete(targets=targets):
            return f"del {', '.join(target_to_text(t) for t in targets)}"
        case ir.Import(module=module, names=[], lazy=lazy):
            return f"{'lazy ' if lazy else ''}import {module}"
        case ir.Import(module=module, names=names, lazy=lazy):
            return f"{'lazy ' if lazy else ''}from {module} import {', '.join(names)}"
        case ir.Pass():
            return "pass"
    raise TypeError(f"cannot print {type(stmt).__name__}")


def params_text(params: list[ir.Param]) -> str:
    """A function's inputs: ``a, b: int = 2, *rest, key=None, **options``."""
    parts = []
    starred = any(p.kind == "args" for p in params)
    for param in params:
        if param.kind == "kwonly" and not starred:
            parts.append("*")
            starred = True
        prefix = {"args": "*", "kwargs": "**"}.get(param.kind, "")
        text = prefix + param.name
        if param.annotation is not None:
            text += f": {expr_to_text(param.annotation)}"
        if param.default is not None:
            sep = " = " if param.annotation is not None else "="
            text += sep + expr_to_text(param.default)
        parts.append(text)
    return ", ".join(parts)


def _type_params(names: list[str]) -> str:
    return f"[{', '.join(names)}]" if names else ""


def pattern_to_text(pattern: ir.Pattern, top: bool = False) -> str:
    """A ``case`` pattern."""
    match pattern:
        case ir.PatternValue(value=value):
            return expr_to_text(value)
        case ir.PatternCapture(name=name):
            return name or "_"
        case ir.PatternStar(name=name):
            return "*" + (name or "_")
        case ir.PatternAs(pattern=inner, name=name):
            text = f"{pattern_to_text(inner)} as {name}"
            return text if top else f"({text})"
        case ir.PatternOr(patterns=patterns):
            text = " | ".join(pattern_to_text(p) for p in patterns)
            return text if top else f"({text})"
        case ir.PatternSequence(patterns=[one]):
            return f"[{pattern_to_text(one)}]"
        case ir.PatternSequence(patterns=patterns):
            return "(" + ", ".join(pattern_to_text(p) for p in patterns) + ")"
        case ir.PatternMapping(keys=keys, patterns=patterns, rest=rest):
            items = [
                f"{expr_to_text(k)}: {pattern_to_text(p)}"
                for k, p in zip(keys, patterns, strict=True)
            ]
            if rest is not None:
                items.append(f"**{rest}")
            return "{" + ", ".join(items) + "}"
        case ir.PatternClass(cls=cls, patterns=patterns, kwd_names=names, kwd_patterns=kwds):
            items = [pattern_to_text(p) for p in patterns]
            items += [f"{n}={pattern_to_text(p)}" for n, p in zip(names, kwds, strict=True)]
            return f"{expr_to_text(cls)}({', '.join(items)})"
    raise TypeError(f"cannot print {type(pattern).__name__}")


def _arguments(args: list[ir.Expr], keywords: list[ir.Keyword]) -> str:
    if len(args) == 1 and not keywords and _is_generator(args[0]):
        return _comprehension_text(args[0], bare=True)  # sum(x for x in y)
    parts = [expr_to_text(a) for a in args]
    parts += [
        f"**{expr_to_text(k.value)}" if k.name is None else f"{k.name}={expr_to_text(k.value)}"
        for k in keywords
    ]
    return ", ".join(parts)


def _is_generator(expr: ir.Expr) -> bool:
    return isinstance(expr, ir.Comprehension) and expr.kind == "generator"


def _comprehension_text(expr: ir.Comprehension, bare: bool = False) -> str:
    head = expr_to_text(expr.elt)
    if expr.kind == "dict" and expr.value is not None:
        head = f"{head}: {expr_to_text(expr.value)}"
    loops = []
    for gen in expr.generators:
        loops.append(
            f"for {target_to_text(gen.target)} in "
            f"{_wrap(gen.iter, _precedence(gen.iter) <= IFEXP_PRECEDENCE)}"
        )
        loops += [f"if {_wrap(c, _precedence(c) <= IFEXP_PRECEDENCE)}" for c in gen.ifs]
    inner = f"{head} {' '.join(loops)}"
    if bare:
        return inner
    brackets = {"list": "[]", "generator": "()"}.get(expr.kind, "{}")
    return f"{brackets[0]}{inner}{brackets[1]}"


def target_to_text(expr: ir.Expr) -> str:
    """Like ``expr_to_text``, but a tuple goes without brackets: ``a, b = b, a``."""
    if isinstance(expr, ir.Tuple) and len(expr.elts) > 1:
        return ", ".join(expr_to_text(e) for e in expr.elts)
    return expr_to_text(expr)


def _precedence(expr: ir.Expr) -> int:
    match expr:
        case ir.BinOp(op=op):
            return PRECEDENCE[op]
        case ir.UnaryOp(op="not"):
            return NOT_PRECEDENCE
        case ir.UnaryOp():
            return UNARY_PRECEDENCE
        case ir.Compare():
            return CMP_PRECEDENCE
        case ir.BoolOp(op=op):
            return BOOL_PRECEDENCE[op]
        case ir.IfExp():
            return IFEXP_PRECEDENCE
        case ir.Lambda() | ir.Yield() | ir.YieldFrom() | ir.NamedExpr():
            return LAMBDA_PRECEDENCE
        case ir.Await():
            return AWAIT_PRECEDENCE
        case ir.Const(value=int() | float() as value) if not isinstance(value, bool) and (
            repr(value).startswith("-")
        ):
            return UNARY_PRECEDENCE  # -1 prints like a minus sign in front of 1
    return ATOM_PRECEDENCE


def _wrap(expr: ir.Expr, needs_parens: bool) -> str:
    text = expr_to_text(expr)
    return f"({text})" if needs_parens else text


def expr_to_text(expr: ir.Expr) -> str:
    match expr:
        case ir.Const(value=str() as value):
            return _str_literal(value)
        case ir.Const(value=value):
            return repr(value)
        case ir.Name(name=name):
            return name
        case ir.Call(func=func, args=args, keywords=keywords):
            return f"{func}({_arguments(args, keywords)})"
        case ir.MethodCall(obj=obj, method=method, args=args, keywords=keywords):
            return f"{_primary(obj)}.{method}({_arguments(args, keywords)})"
        case ir.Lambda(params=params, body=body):
            inputs = params_text(params)
            return (
                f"lambda {inputs}: {expr_to_text(body)}"
                if inputs
                else f"lambda: {expr_to_text(body)}"
            )
        case ir.Yield(value=None):
            return "yield"
        case ir.Yield(value=value):
            return f"yield {target_to_text(value)}"
        case ir.YieldFrom(value=value):
            return f"yield from {expr_to_text(value)}"
        case ir.Await(value=value):
            return "await " + _wrap(value, _precedence(value) < ATOM_PRECEDENCE)
        case ir.NamedExpr(target=target, value=value):
            # bare: an operand gets brackets from its precedence; a statement of its own or
            # the right side of `=` must have them (Python's rule), see _simple_stmt_text
            return f"{target.name} := {expr_to_text(value)}"
        case ir.TString(parts=parts):
            return "t" + _fstring(parts)[1:]
        case ir.Attribute(value=value, attr=attr):
            return f"{_primary(value)}.{attr}"
        case ir.List(elts=elts):
            return "[" + ", ".join(expr_to_text(e) for e in elts) + "]"
        case ir.Tuple(elts=[one]):
            return f"({expr_to_text(one)},)"
        case ir.Tuple(elts=elts):
            return "(" + ", ".join(expr_to_text(e) for e in elts) + ")"
        case ir.Set(elts=[]):
            return "set()"
        case ir.Set(elts=elts):
            return "{" + ", ".join(expr_to_text(e) for e in elts) + "}"
        case ir.Dict(keys=keys, values=values):
            items = [
                f"**{_wrap(v, _precedence(v) < ATOM_PRECEDENCE)}"
                if k is None
                else f"{expr_to_text(k)}: {expr_to_text(v)}"
                for k, v in zip(keys, values, strict=True)
            ]
            return "{" + ", ".join(items) + "}"
        case ir.Starred(value=value):
            return "*" + _wrap(value, _precedence(value) < ATOM_PRECEDENCE)
        case ir.Comprehension():
            return _comprehension_text(expr)
        case ir.Subscript(value=value, index=index):
            return f"{_primary(value)}[{target_to_text(index)}]"
        case ir.Slice(lower=lower, upper=upper, step=step):
            text = ":".join("" if p is None else expr_to_text(p) for p in (lower, upper))
            return text if step is None else f"{text}:{expr_to_text(step)}"
        case ir.BinOp(op="**", left=left, right=right):
            # right-associative, and binds tighter than a minus on its left: -(2 ** 2)
            left_text = _wrap(left, _precedence(left) <= POW_PRECEDENCE)
            right_text = _wrap(right, _precedence(right) < UNARY_PRECEDENCE)
            return f"{left_text} ** {right_text}"
        case ir.UnaryOp(op="not", operand=operand):
            return "not " + _wrap(operand, _precedence(operand) < NOT_PRECEDENCE)
        case ir.Compare(left=left, ops=ops, comparators=comparators):
            parts = [_wrap(left, _precedence(left) <= CMP_PRECEDENCE)]
            for op, right in zip(ops, comparators, strict=True):
                parts += [op, _wrap(right, _precedence(right) <= CMP_PRECEDENCE)]
            return " ".join(parts)
        case ir.BoolOp(op=op, values=values):
            prec = BOOL_PRECEDENCE[op]
            return f" {op} ".join(_wrap(v, _precedence(v) <= prec) for v in values)
        case ir.IfExp(test=test, body=body, orelse=orelse):
            body_text = _wrap(body, _precedence(body) <= IFEXP_PRECEDENCE)
            test_text = _wrap(test, _precedence(test) <= IFEXP_PRECEDENCE)
            return f"{body_text} if {test_text} else {expr_to_text(orelse)}"
        case ir.FString(parts=parts):
            return _fstring(parts)
        case ir.FormattedValue():
            return _fstring([expr])
        case ir.BinOp(op=op, left=left, right=right):
            prec = PRECEDENCE[op]
            # left-associative: same precedence on the right needs brackets
            left_text = _wrap(left, _precedence(left) < prec)
            right_text = _wrap(right, _precedence(right) <= prec)
            return f"{left_text} {op} {right_text}"
        case ir.UnaryOp(op=op, operand=operand):
            return op + _wrap(operand, _precedence(operand) < UNARY_PRECEDENCE)
    raise TypeError(f"cannot print {type(expr).__name__}")


def _primary(expr: ir.Expr) -> str:
    """``expr`` on the left of ``.method()`` or ``[...]``; ``5.upper`` would not parse."""
    number = isinstance(expr, ir.Const) and isinstance(expr.value, int | float)
    return _wrap(expr, number or _precedence(expr) < ATOM_PRECEDENCE)


def _fstring(parts: list[ir.Expr]) -> str:
    """An f-string. Fields avoid the outer quote, which Python before 3.12 requires."""
    fields: list[tuple[bool, str]] = []  # (is a {field}, text)
    for part in parts:
        if isinstance(part, ir.FormattedValue):
            text = expr_to_text(part.value)
            if text.startswith("{"):
                text = " " + text
            if part.conversion:
                text += f"!{part.conversion}"
            if part.spec:
                text += f":{part.spec}"
            fields.append((True, "{" + text + "}"))
        elif isinstance(part, ir.Const) and isinstance(part.value, str):
            text = part.value.replace("\\", "\\\\").replace("{", "{{").replace("}", "}}")
            text = text.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
            fields.append((False, text))
        else:
            raise TypeError("f-string parts must be text or {fields}")
    inner = "".join(text for is_field, text in fields if is_field)
    quote = "'" if '"' in inner and "'" not in inner else '"'
    body = "".join(
        text if is_field else text.replace(quote, "\\" + quote) for is_field, text in fields
    )
    return f"f{quote}{body}{quote}"


def _str_literal(value: str) -> str:
    text = repr(value)
    if text.startswith("'") and '"' not in value:
        return '"' + text[1:-1] + '"'
    return text


# --- blocks --------------------------------------------------------------------


def outline(program: ir.Program) -> Iterator[tuple[int, ir.Stmt]]:
    """Statements in order with their nesting depth."""

    def visit(stmts: list[ir.Stmt], depth: int) -> Iterator[tuple[int, ir.Stmt]]:
        for stmt in stmts:
            yield depth, stmt
            if isinstance(stmt, ir.For | ir.While | ir.FunctionDef | ir.ClassDef | ir.With):
                yield from visit(stmt.body, depth + 1)
            elif isinstance(stmt, ir.Match):
                for case in stmt.cases:
                    yield from visit(case.body, depth + 1)
            elif isinstance(stmt, ir.If):
                yield from visit(stmt.body, depth + 1)
                yield from visit(stmt.orelse, depth + 1)
            elif isinstance(stmt, ir.Try):
                yield from visit(stmt.body, depth + 1)
                for handler in stmt.handlers:
                    yield from visit(handler.body, depth + 1)
                yield from visit(stmt.orelse, depth + 1)
                yield from visit(stmt.finalbody, depth + 1)

    yield from visit(program.body, 0)


def block_label(stmt: ir.Stmt) -> str:
    """How a statement reads as a block."""
    match stmt:
        case ir.ExprStmt(value=ir.Call(func=func, args=args)):
            return " ".join([func.replace("_", " "), *(expr_to_text(a) for a in args)])
        case ir.ExprStmt(value=value):
            return f"value {expr_to_text(value)}"
        case ir.Assign(target=target, value=value):
            return f"set {target_to_text(target)} to {target_to_text(value)}"
        case ir.AugAssign(target=target, op=op, value=value):
            return f"change {target_to_text(target)} by {op}{expr_to_text(value)}"
        case ir.FunctionDef(name=name, params=params, is_async=True):
            return f"teach async {name}({', '.join(p.name for p in params)})"
        case ir.FunctionDef(name=name, params=params):
            return f"teach {name}({', '.join(p.name for p in params)})"
        case ir.ClassDef(name=name):
            return f"class {name}"
        case ir.With(items=items):
            return "with " + ", ".join(expr_to_text(i.context) for i in items)
        case ir.Match(subject=subject):
            return f"match {expr_to_text(subject)}"
        case ir.AnnAssign() | ir.Nonlocal() | ir.TypeAlias():
            return _simple_stmt_text(stmt)
        case ir.Return(value=None):
            return "give back"
        case ir.Return(value=value):
            return f"give back {target_to_text(value)}"
        case ir.Break():
            return "stop the loop"
        case ir.Continue():
            return "skip to the next turn"
        case ir.Try():
            return "try / if it goes wrong"
        case ir.Raise() | ir.Assert() | ir.Delete() | ir.Global() | ir.Import():
            return _simple_stmt_text(stmt)
        case ir.For(target=ir.Name() as target, iter=ir.Call(func="range", args=[count])):
            return f"repeat {expr_to_text(count)} times ({target.name} counts)"
        case ir.For(target=target, iter=iterable):
            return f"for each {target_to_text(target)} in {expr_to_text(iterable)}"
        case ir.If(test=test, orelse=[]):
            return f"if {expr_to_text(test)}"
        case ir.If(test=test):
            return f"if {expr_to_text(test)} / else"
        case ir.While(test=test):
            return f"repeat while {expr_to_text(test)}"
        case ir.Comment(text=text):
            return f"note: {text}"
        case ir.Pass():
            return "do nothing"
        case ir.RawCode(reason=reason):
            return f"raw code ({reason})"
    return type(stmt).__name__
