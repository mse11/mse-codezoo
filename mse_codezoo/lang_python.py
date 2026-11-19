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

BASELINE = (3, 11)
INDENT = "    "

BIN_OPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
}
UNARY_OPS: dict[type[ast.unaryop], str] = {ast.USub: "-", ast.UAdd: "+"}
PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2, "//": 2, "%": 2}
UNARY_PRECEDENCE = 3
ATOM_PRECEDENCE = 4

FRIENDLY = {
    # statements
    "If": "`if` statements",
    "While": "`while` loops",
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
    "AsyncFor": "async loops",
    "AsyncWith": "async `with` blocks",
    "TypeAlias": "`type` aliases",
    # expressions
    "Compare": "comparisons like `<` or `==`",
    "BoolOp": "`and` / `or`",
    "List": "lists",
    "Tuple": "tuples",
    "Dict": "dictionaries",
    "Set": "sets",
    "Attribute": "dots like `a.b`",
    "Subscript": "indexing like `a[0]`",
    "JoinedStr": "f-strings",
    "Lambda": "`lambda`",
    "ListComp": "comprehensions",
    "SetComp": "comprehensions",
    "DictComp": "comprehensions",
    "GeneratorExp": "comprehensions",
    "IfExp": "`x if y else z`",
    "Await": "`await`",
    "NamedExpr": "`:=`",
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


def parse(text: str, version: tuple[int, int] = BASELINE) -> ParseResult:
    """Parse Python ``text`` into IR, accepting only syntax available in ``version``."""
    try:
        tree = ast.parse(text, feature_version=version)
    except SyntaxError as exc:
        line = exc.lineno or 1
        message = f"Python can't read line {line}: {exc.msg}."
        return ParseResult(None, [Diagnostic(line, max((exc.offset or 1) - 1, 0), message)])
    except ValueError as exc:  # e.g. null bytes in the source
        return ParseResult(None, [Diagnostic(1, 0, f"Python can't read this file: {exc}.")])
    converter = _Converter(text)
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
    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()
        self.new_id = ir.Ids()
        self.diagnostics: list[Diagnostic] = []
        self.positions: dict[str, Span] = {}
        self.comments, self.inline = _scan_comments(text)

    def program(self, tree: ast.Module) -> ir.Program:
        program_id = self.new_id()
        return ir.Program(id=program_id, body=self.body(tree.body, indent=0, stop_line=math.inf))

    def body(self, stmts: list[ast.stmt], indent: int, stop_line: float) -> list[ir.Stmt]:
        out: list[ir.Stmt] = []
        for i, node in enumerate(stmts):
            out += self.take_comments(before=node.lineno)
            next_line = stmts[i + 1].lineno if i + 1 < len(stmts) else stop_line
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
        self.positions[stmt_id] = self.span(node)
        try:
            result = self._stmt(node, stmt_id, next_line)
        except Unsupported as exc:
            end = node.end_lineno or node.lineno
            # inner comments are part of the raw text; don't emit them twice
            self.comments = [c for c in self.comments if c[0] > end]
            text = textwrap.dedent("\n".join(self.lines[node.lineno - 1 : end]))
            reason = str(exc)
            self.diagnostics.append(
                Diagnostic(
                    node.lineno,
                    node.col_offset,
                    f"CodeZoo can't turn {reason} into blocks yet; kept as raw code.",
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
            case ast.Assign(targets=[ast.Name() as target], value=value):
                return ir.Assign(id=stmt_id, target=self.name(target), value=self.expr(value))
            case ast.AugAssign(target=ast.Name() as target, op=op, value=value) if (
                type(op) in BIN_OPS
            ):
                return ir.AugAssign(
                    id=stmt_id,
                    target=self.name(target),
                    op=BIN_OPS[type(op)],
                    value=self.expr(value),
                )
            case ast.For(target=ast.Name() as target, iter=iterable, body=body, orelse=[]):
                header_target = self.name(target)
                header_iter = self.expr(iterable)
                return ir.For(
                    id=stmt_id,
                    target=header_target,
                    iter=header_iter,
                    body=self.body(body, indent=body[0].col_offset, stop_line=next_line),
                )
            case ast.Pass():
                return ir.Pass(id=stmt_id)
        raise Unsupported(friendly_name(node))

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
            case ast.Call(func=ast.Name(id=func), args=args, keywords=[]):
                if any(isinstance(arg, ast.Starred) for arg in args):
                    raise Unsupported("`*` unpacking")
                return ir.Call(id=expr_id, func=func, args=[self.expr(a) for a in args])
            case ast.Call():
                raise Unsupported("this kind of call")
            case ast.BinOp(left=left, op=op, right=right) if type(op) in BIN_OPS:
                return ir.BinOp(
                    id=expr_id, op=BIN_OPS[type(op)], left=self.expr(left), right=self.expr(right)
                )
            case ast.BinOp(op=ast.Pow()):
                raise Unsupported("powers (`**`)")
            case ast.UnaryOp(op=op, operand=operand) if type(op) in UNARY_OPS:
                return ir.UnaryOp(id=expr_id, op=UNARY_OPS[type(op)], operand=self.expr(operand))
            case ast.Constant():
                raise Unsupported("this kind of value")
        raise Unsupported(friendly_name(node))


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
                self.emit(f"{pad}for {target.name} in {expr_to_text(iterable)}:", stmt)
                self.body(body, depth + 1)
            case _:
                self.emit(pad + _simple_stmt_text(stmt), stmt)
        end = len(self.lines)
        if end >= start:
            self.source_map[stmt.id] = Span(start, len(pad), end, len(self.lines[end - 1]))

    def emit(self, line: str, stmt: ir.Stmt) -> None:
        if stmt.comment is not None:
            line += f"  # {stmt.comment}" if stmt.comment else "  #"
        self.lines.append(line)


def _simple_stmt_text(stmt: ir.Stmt) -> str:
    match stmt:
        case ir.ExprStmt(value=value):
            return expr_to_text(value)
        case ir.Assign(target=target, value=value):
            return f"{target.name} = {expr_to_text(value)}"
        case ir.AugAssign(target=target, op=op, value=value):
            return f"{target.name} {op}= {expr_to_text(value)}"
        case ir.Pass():
            return "pass"
    raise TypeError(f"cannot print {type(stmt).__name__}")


def _precedence(expr: ir.Expr) -> int:
    if isinstance(expr, ir.BinOp):
        return PRECEDENCE[expr.op]
    if isinstance(expr, ir.UnaryOp):
        return UNARY_PRECEDENCE
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
        case ir.Call(func=func, args=args):
            return f"{func}({', '.join(expr_to_text(a) for a in args)})"
        case ir.BinOp(op=op, left=left, right=right):
            prec = PRECEDENCE[op]
            # left-associative: same precedence on the right needs brackets
            left_text = _wrap(left, _precedence(left) < prec)
            right_text = _wrap(right, _precedence(right) <= prec)
            return f"{left_text} {op} {right_text}"
        case ir.UnaryOp(op=op, operand=operand):
            return op + _wrap(operand, _precedence(operand) < UNARY_PRECEDENCE)
    raise TypeError(f"cannot print {type(expr).__name__}")


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
            if isinstance(stmt, ir.For):
                yield from visit(stmt.body, depth + 1)

    yield from visit(program.body, 0)


def block_label(stmt: ir.Stmt) -> str:
    """How a statement reads as a block."""
    match stmt:
        case ir.ExprStmt(value=ir.Call(func=func, args=args)):
            return " ".join([func.replace("_", " "), *(expr_to_text(a) for a in args)])
        case ir.ExprStmt(value=value):
            return f"value {expr_to_text(value)}"
        case ir.Assign(target=target, value=value):
            return f"set {target.name} to {expr_to_text(value)}"
        case ir.AugAssign(target=target, op=op, value=value):
            return f"change {target.name} by {op}{expr_to_text(value)}"
        case ir.For(target=target, iter=ir.Call(func="range", args=[count])):
            return f"repeat {expr_to_text(count)} times ({target.name} counts)"
        case ir.For(target=target, iter=iterable):
            return f"for each {target.name} in {expr_to_text(iterable)}"
        case ir.Comment(text=text):
            return f"note: {text}"
        case ir.Pass():
            return "do nothing"
        case ir.RawCode(reason=reason):
            return f"raw code ({reason})"
    return type(stmt).__name__
