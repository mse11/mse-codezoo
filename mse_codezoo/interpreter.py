"""Step-by-step evaluator for the IR.

Each statement produces a ``Step`` so clients can highlight the block and line and animate
the world. Learner code never reaches ``exec`` or ``eval``: only the builtins and methods
listed here and the world actions passed in exist. Learner functions run on our own
call stack with a depth limit; ``break``, ``continue`` and ``return`` travel as signals.
Errors the learner can catch with ``try`` carry a real Python exception (``ValueError``,
a world's ``CrackError``); the zoo's own limits (steps, depth, sizes) can't be caught.
Standard library only.
"""

from __future__ import annotations

import difflib
import math
import re
import string
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from mse_codezoo import ir
from mse_codezoo.i18n import t

MAX_STEPS = 10_000
MAX_TEXT = 10_000
MAX_ITEMS = 10_000  # items in one list, tuple, set or dict
MAX_INT = 10**100
MAX_INT_BITS = MAX_INT.bit_length()
MAX_DEPTH = 40  # learner function calls inside each other
MAX_NOTE = 80

# Methods learners may call, per kind of value; everything else is unknown.
STR_METHODS = (
    "upper",
    "lower",
    "title",
    "capitalize",
    "swapcase",
    "strip",
    "lstrip",
    "rstrip",
    "replace",
    "count",
    "find",
    "index",
    "startswith",
    "endswith",
    "isdigit",
    "isalpha",
    "isalnum",
    "isspace",
    "isupper",
    "islower",
    "center",
    "ljust",
    "rjust",
    "zfill",
    "format",
    "split",
    "join",
)
FLOAT_METHODS = ("is_integer",)
LIST_METHODS = (
    "append",
    "pop",
    "insert",
    "remove",
    "index",
    "extend",
    "count",
    "sort",
    "reverse",
    "clear",
    "copy",
)
TUPLE_METHODS = ("count", "index")
DICT_METHODS = (
    "get",
    "setdefault",
    "update",
    "keys",
    "values",
    "items",
    "pop",
    "clear",
    "copy",
)
SET_METHODS = (
    "add",
    "remove",
    "discard",
    "union",
    "intersection",
    "difference",
    "symmetric_difference",
    "issubset",
    "issuperset",
    "clear",
    "copy",
)
PAD_METHODS = ("center", "ljust", "rjust", "zfill")
GROWING_METHODS = ("append", "insert", "extend", "update", "add", "setdefault", "union")
METHOD_KEYWORDS = {"sort": ("key", "reverse"), "split": ("sep", "maxsplit")}
PRINT_KEYWORDS = ("sep", "end")
BUILTIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "print": PRINT_KEYWORDS,
    "sorted": ("key", "reverse"),
    "min": ("key", "default"),
    "max": ("key", "default"),
    "enumerate": ("start",),
    "zip": ("strict",),
    "sum": ("start",),
    "round": ("ndigits",),
    "int": ("base",),
}
CONSUMING = ("list", "tuple", "set", "dict", "sorted", "sum", "any", "all", "min", "max")
NUMBER_IN_SPEC = re.compile(r"\d+")
EXCEPTIONS: dict[str, type[BaseException]] = {
    cls.__name__: cls
    for cls in (
        Exception,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        ZeroDivisionError,
        NameError,
        AssertionError,
        RuntimeError,
        LookupError,
        ArithmeticError,
    )
}


class LearnerError(Exception):
    """A problem in the learner's program, worded for the learner.

    ``kind`` sorts mistakes for the grown-up report: ``bump``, ``unknown_name``,
    ``too_many_steps``, ``too_deep``, ``type``, ``raised`` or ``other``.
    ``exception`` is the Python exception a ``try`` can catch; ``None`` means the error
    can't be caught (a bump, or one of the zoo's limits). ``traceback`` lists
    ``(function, statement id)`` from the outside in, like Python's own traceback.
    """

    def __init__(
        self,
        message: str,
        node_id: str | None = None,
        kind: str = "other",
        exception: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.node_id = node_id
        self.kind = kind
        self.exception = exception
        self.traceback: list[tuple[str, str]] = []


class _Signal(BaseException):  # noqa: N818 - control flow, not an error
    """``break``, ``continue`` and ``return`` on their way to the loop or call."""


class _Break(_Signal):
    pass


class _Continue(_Signal):
    pass


class _Return(_Signal):
    def __init__(self, value: Any) -> None:
        super().__init__()
        self.value = value


@dataclass
class Step:
    node_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None
    error: str | None = None


@dataclass
class RunResult:
    steps: list[Step]
    output: list[str]
    error: LearnerError | None

    @property
    def ok(self) -> bool:
        return self.error is None


class function:  # noqa: N801 - named like Python's own, so `type(f)` shows <class 'function'>
    """A function the learner taught with ``def``."""

    def __init__(
        self,
        runner: Runner,
        node: ir.FunctionDef,
        defaults: list[Any],
        globals_: dict[str, Any],
        closures: list[dict[str, Any]],
    ) -> None:
        self.runner = runner
        self.node = node
        self.name = node.name
        self.defaults = defaults  # one per param; _NO_DEFAULT where there is none
        self.globals = globals_
        self.closures = closures

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # e.g. sorted(logs, key=size)
        return self.runner.invoke(self, list(args), kwargs)

    def __repr__(self) -> str:
        return f"<function {self.name}>"


function.__module__ = "builtins"


class module:  # noqa: N801 - like Python's own module type
    """A helper file brought in with ``import``."""

    def __init__(self, name: str, names: dict[str, Any]) -> None:
        self.name = name
        self.names = names

    def __repr__(self) -> str:
        return f"<module '{self.name}'>"


module.__module__ = "builtins"

_NO_DEFAULT = object()


@dataclass
class Frame:
    """One running learner function (or a comprehension's own little scope)."""

    name: str
    locals: dict[str, Any]
    local_names: set[str]
    global_names: set[str]
    globals: dict[str, Any]
    closures: list[dict[str, Any]]
    comprehension: bool = False
    current: str | None = None  # the statement running in this frame


def describe(value: Any) -> str:
    """A learner-friendly name for the kind of a value."""
    if isinstance(value, bool):
        return t("a yes/no value")
    if isinstance(value, int):
        return t("a whole number")
    if isinstance(value, float):
        return t("a decimal number")
    if isinstance(value, str):
        return t("text")
    if value is None:
        return t("nothing (`None`)")
    if isinstance(value, range):
        return t("a range")
    if isinstance(value, list):
        return t("a list")
    if isinstance(value, tuple):
        return t("a tuple")
    if isinstance(value, dict):
        return t("a dictionary")
    if isinstance(value, set | frozenset):
        return t("a set")
    if isinstance(value, function):
        return t("a function")
    if isinstance(value, module):
        return t("a helper file")
    if isinstance(value, BaseException):
        return t("an error")
    if isinstance(value, type):
        return t("a type")
    if callable(value):
        return t("a command")
    return type(value).__name__


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= MAX_NOTE else text[: MAX_NOTE - 3] + "..."


def _range(*args: Any) -> range:
    return range(*args)


def _extreme(pick: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    # min/max over a huge range would loop inside Python without counting steps
    if len(args) == 1 and isinstance(args[0], range) and not kwargs:
        values = args[0]
        if not values:
            raise ValueError("the range is empty")
        return pick(values[0], values[-1])
    return pick(*args, **kwargs)


def _type(value: Any) -> type:
    return type(value)


def _check_spec(spec: str) -> None:
    """Refuse format specs that would build enormous text, like ``:>999999999``."""
    for number in NUMBER_IN_SPEC.findall(spec):
        if int(number) > MAX_TEXT:
            raise LearnerError(t("That text would be far too long for the zoo."))


def _too_long() -> LearnerError:
    return LearnerError(t("That text would be far too long for the zoo."))


def _too_many_items() -> LearnerError:
    return LearnerError(t("That collection would hold far too many things for the zoo."))


def assigned_names(stmts: list[ir.Stmt]) -> set[str]:
    """Names a function body gives values to; Python makes these local to the function."""
    names: set[str] = set()

    def targets(node: ir.Expr) -> None:
        if isinstance(node, ir.Name):
            names.add(node.name)
        elif isinstance(node, ir.Tuple):
            for item in node.elts:
                targets(item)
        elif isinstance(node, ir.Starred):
            targets(node.value)

    def visit(body: list[ir.Stmt]) -> None:
        for stmt in body:
            match stmt:
                case ir.Assign(target=target) | ir.AugAssign(target=target):
                    targets(target)
                case ir.For(target=target, body=inner):
                    targets(target)
                    visit(inner)
                case ir.Delete(targets=items):
                    for item in items:
                        targets(item)
                case ir.FunctionDef(name=name):
                    names.add(name)  # its body has its own scope
                case ir.Import(module=module_name, names=imported):
                    names.update(imported or [module_name])
                case ir.If(body=inner, orelse=orelse):
                    visit(inner)
                    visit(orelse)
                case ir.While(body=inner):
                    visit(inner)
                case ir.Try(body=inner, handlers=handlers, orelse=orelse, finalbody=final):
                    visit(inner)
                    for handler in handlers:
                        if handler.name:
                            names.add(handler.name)
                        visit(handler.body)
                    visit(orelse)
                    visit(final)

    visit(stmts)
    return names


def global_names(stmts: list[ir.Stmt]) -> set[str]:
    found: set[str] = set()
    for node in stmts:
        for inner in ir.walk(node):
            if isinstance(inner, ir.FunctionDef) and inner is not node:
                continue
            if isinstance(inner, ir.Global):
                found.update(inner.names)
    return found


class Runner:
    """Runs one program. Call ``execute()``; afterwards read ``steps``, ``output``, ``error``.

    ``modules`` maps a helper file's name (``"tricks"``) to its Python source or IR, for
    ``import tricks``. ``on_step`` sees every step as it happens.
    """

    def __init__(
        self,
        program: ir.Program,
        actions: dict[str, Callable[..., Any]] | None = None,
        drain_events: Callable[[], list[dict[str, Any]]] | None = None,
        max_steps: int = MAX_STEPS,
        *,
        modules: dict[str, str | ir.Program] | None = None,
        on_step: Callable[[Step], None] | None = None,
    ) -> None:
        self.program = program
        self.actions = dict(actions or {})
        self.drain_world = drain_events or list
        self.max_steps = max_steps
        self.modules_source = dict(modules or {})
        self.loaded: dict[str, module] = {}
        self.on_step = on_step
        self.env: dict[str, Any] = {}
        self.globals = self.env  # the module whose code is running now
        self.frames: list[Frame] = []
        self.top_current: str | None = None
        self.handling: list[LearnerError] = []  # errors being handled by `except`
        self.events: list[dict[str, Any]] = []  # the interpreter's own: call, return
        self.steps: list[Step] = []
        self.output: list[str] = []
        self._partial = ""  # printed text after the last newline
        self.count = 0
        self.error: LearnerError | None = None
        self.builtins: dict[str, Any] = {
            "print": self._print,
            "range": _range,
            "len": len,
            "abs": abs,
            "min": lambda *a, **k: _extreme(min, *a, **k),
            "max": lambda *a, **k: _extreme(max, *a, **k),
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "round": round,
            "type": _type,
            "list": list,
            "tuple": tuple,
            "dict": dict,
            "set": set,
            "sorted": sorted,
            "sum": sum,
            "enumerate": enumerate,
            "zip": zip,
            "reversed": reversed,
            "any": any,
            "all": all,
            "isinstance": isinstance,
            **EXCEPTIONS,
        }

    # --- running -------------------------------------------------------------

    def execute(self) -> None:
        try:
            try:
                self._body(self.program.body)
            except (_Break, _Continue) as signal:
                word = "break" if isinstance(signal, _Break) else "continue"
                raise LearnerError(
                    t("`{word}` only works inside a loop.", word=word), self.top_current
                ) from None
            except _Return:
                raise LearnerError(
                    t("`return` only works inside a function (`def`)."), self.top_current
                ) from None
            except RecursionError:
                raise LearnerError(
                    t("Your program went too deep for the zoo to follow."),
                    self.top_current,
                    kind="too_deep",
                ) from None
        except LearnerError as exc:
            self.error = exc
            if exc.exception is not None and exc.kind == "raised":
                exc.message = self._uncaught_message(exc)
            self._emit(Step(exc.node_id or self.program.id, self._drain(), error=exc.message))
        finally:
            if self._partial:
                self.output.append(self._partial)
                self._partial = ""

    def run_steps(self) -> Iterator[Step]:
        """All steps, after running the whole program."""
        self.execute()
        yield from self.steps

    def _emit(self, step: Step) -> None:
        self.steps.append(step)
        if self.on_step is not None:
            self.on_step(step)

    def _drain(self) -> list[dict[str, Any]]:
        events, self.events = self.events, []
        return [*self.drain_world(), *events] if events else self.drain_world()

    def _step(self, stmt: ir.Node, note: str | None = None) -> None:
        self._emit(Step(stmt.id, self._drain(), note=note))

    def _uncaught_message(self, exc: LearnerError) -> str:
        error = exc.exception
        assert error is not None
        detail = str(error)
        name = type(error).__name__
        if detail:
            return t("`{kind}` happened and no `except` caught it: {why}", kind=name, why=detail)
        return t("`{kind}` happened and no `except` caught it.", kind=name)

    # --- statements --------------------------------------------------------

    def _body(self, stmts: list[ir.Stmt]) -> None:
        for stmt in stmts:
            self._stmt(stmt)

    def _set_current(self, stmt_id: str) -> None:
        for frame in reversed(self.frames):
            if not frame.comprehension:
                frame.current = stmt_id
                return
        self.top_current = stmt_id

    def _stmt(self, stmt: ir.Stmt) -> None:
        if isinstance(stmt, ir.Comment | ir.Pass):
            return
        self._set_current(stmt.id)
        try:
            self._tick(stmt)
            self._exec(stmt)
        except LearnerError as exc:
            if exc.node_id is None:
                exc.node_id = stmt.id
                exc.traceback = self._traceback()
            raise
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, RuntimeError) as exc:
            # a safety net: Python refused something we didn't check for ourselves
            raise LearnerError(
                t("Python couldn't do that: {why}", why=exc),
                stmt.id,
                kind="type",
                exception=exc,
            ) from None

    def _traceback(self) -> list[tuple[str, str]]:
        trace = [("<program>", self.top_current or self.program.id)]
        trace += [(f.name, f.current or "") for f in self.frames if not f.comprehension]
        return trace

    def _exec(self, stmt: ir.Stmt) -> None:
        match stmt:
            case ir.ExprStmt(value=value):
                self._eval(value)
                self._step(stmt)
            case ir.Assign(target=target, value=value):
                result = self._eval(value)
                self._assign(target, result)
                self._step(stmt, note=self._note(target, result))
            case ir.AugAssign(target=target, op=op, value=value):
                self._aug_assign(stmt, target, op, value)
            case ir.For(target=target, iter=iterable, body=body):
                self._for(stmt, target, iterable, body)
            case ir.If(test=test, body=body, orelse=orelse):
                passed = self._test(test)
                self._step(stmt, note=f"-> {passed}")
                self._body(body if passed else orelse)
            case ir.While(test=test, body=body):
                while True:
                    passed = self._test(test)
                    self._step(stmt, note=f"-> {passed}")
                    if not passed:
                        break
                    try:
                        self._body(body)
                    except _Break:
                        break
                    except _Continue:
                        pass
                    self._tick(stmt)
            case ir.Break():
                self._step(stmt)
                raise _Break
            case ir.Continue():
                self._step(stmt)
                raise _Continue
            case ir.FunctionDef():
                self._define(stmt)
            case ir.Return(value=value):
                result = None if value is None else self._eval(value)
                self._step(stmt, note=f"-> {_short(result)}")
                raise _Return(result)
            case ir.Global():
                if self.frames:
                    self.frames[-1].global_names.update(stmt.names)
            case ir.Try():
                self._try(stmt)
            case ir.Raise(exc=exc):
                self._step(stmt)
                self._raise(exc)
            case ir.Assert(test=test, msg=msg):
                passed = self._test(test)
                self._step(stmt, note=f"-> {passed}")
                if not passed:
                    detail = "" if msg is None else self._eval(msg)
                    error = AssertionError(detail) if msg is not None else AssertionError()
                    raise LearnerError(
                        t("A check with `assert` failed: {why}", why=detail)
                        if detail != ""
                        else t("A check with `assert` failed."),
                        kind="raised",
                        exception=error,
                    )
            case ir.Delete(targets=targets):
                for target in targets:
                    self._delete(target)
                self._step(stmt)
            case ir.Import():
                self._import(stmt)
                self._step(stmt)
            case ir.RawCode(reason=reason):
                raise LearnerError(t("CodeZoo can't run {what} yet.", what=t(reason)))
            case _:
                raise LearnerError(t("CodeZoo can't run `{what}` yet.", what=type(stmt).__name__))

    def _note(self, target: ir.Expr, value: Any) -> str:
        from mse_codezoo.lang_python import target_to_text

        return f"{target_to_text(target)} = {_short(value)}"

    def _tick(self, stmt: ir.Node) -> None:
        self.count += 1
        if self.count > self.max_steps:
            raise LearnerError(
                t(
                    "Your program took more than {count} steps. Is a loop running too many times?",
                    count=self.max_steps,
                ),
                stmt.id,
                kind="too_many_steps",
            )

    def _for(self, stmt: ir.For, target: ir.Expr, iterable: ir.Expr, body: list[ir.Stmt]) -> None:
        values = self._eval(iterable)
        if not self._iterable(values):
            raise LearnerError(
                t(
                    "A `for` loop needs something to go through, like `range(5)`, not {what}.",
                    what=describe(values),
                ),
                kind="type",
                exception=TypeError(f"'{type(values).__name__}' object is not iterable"),
            )
        first = True
        for item in values:
            if not first:
                self._tick(stmt)
            first = False
            self._assign(target, item)
            self._step(stmt, note=self._note(target, item))
            try:
                self._body(body)
            except _Break:
                break
            except _Continue:
                continue

    @staticmethod
    def _iterable(value: Any) -> bool:
        if isinstance(value, str | bytes) or callable(value):
            return isinstance(value, str)
        try:
            iter(value)
        except TypeError:
            return False
        return True

    def _test(self, expr: ir.Expr) -> bool:
        value = self._eval(expr)
        if callable(value) and not isinstance(value, type) and isinstance(expr, ir.Name):
            raise LearnerError(
                t(
                    "`{name}` is a command, so it is always true. "
                    "Add brackets to ask it: `{name}()`.",
                    name=expr.name,
                ),
                kind="type",
            )
        return bool(value)

    # --- names and scopes ------------------------------------------------------

    def _frame(self) -> Frame | None:
        return self.frames[-1] if self.frames else None

    def _lookup(self, name: str) -> Any:
        frame = self._frame()
        if frame is not None:
            if name in frame.locals:
                return frame.locals[name]
            if name in frame.local_names and name not in frame.global_names:
                function_name = next(
                    (f.name for f in reversed(self.frames) if not f.comprehension), frame.name
                )
                raise LearnerError(
                    t(
                        "`{name}` is used in `{function}` before it gets a value there. "
                        "To change the `{name}` outside, write `global {name}` first.",
                        name=name,
                        function=function_name,
                    ),
                    kind="unknown_name",
                    exception=NameError(f"cannot access local variable '{name}'"),
                )
            for scope in frame.closures:
                if name in scope:
                    return scope[name]
        scopes = (frame.globals if frame else self.globals, self.builtins, self.actions)
        for scope in scopes:
            if name in scope:
                return scope[name]
        # the learner's own names and the animal's commands are the likeliest typos
        known = [*self.globals, *(frame.locals if frame else {}), *self.actions]
        close = difflib.get_close_matches(name, known, n=1)
        close = close or difflib.get_close_matches(name, list(self.builtins), n=1)
        hint = t(" Did you mean `{name}`?", name=close[0]) if close else ""
        raise LearnerError(
            t("I don't know `{name}`.{hint}", name=name, hint=hint),
            kind="unknown_name",
            exception=NameError(f"name '{name}' is not defined"),
        )

    def _scope_for(self, name: str) -> dict[str, Any]:
        frame = self._frame()
        if frame is None:
            return self.globals
        if name in frame.global_names:
            return frame.globals
        return frame.locals

    def _assign(self, target: ir.Expr, value: Any) -> None:
        match target:
            case ir.Name(name=name):
                self._scope_for(name)[name] = value
            case ir.Subscript(value=container, index=index):
                self._set_item(self._eval(container), index, value)
            case ir.Tuple(elts=elts):
                self._unpack(elts, value)
            case _:
                raise LearnerError(t("You can't give a value to that."), kind="type")

    def _unpack(self, elts: list[ir.Expr], value: Any) -> None:
        if not self._iterable(value):
            raise LearnerError(
                t(
                    "{what} can't be split into {count} parts.",
                    what=describe(value).capitalize(),
                    count=len(elts),
                ),
                kind="type",
                exception=TypeError(f"cannot unpack non-iterable {type(value).__name__} object"),
            )
        items = list(value)
        star = next((i for i, e in enumerate(elts) if isinstance(e, ir.Starred)), None)
        if star is None:
            if len(items) != len(elts):
                raise LearnerError(
                    t(
                        "There are {have} values here, but {want} names to give them to.",
                        have=len(items),
                        want=len(elts),
                    ),
                    kind="type",
                    exception=ValueError(
                        f"too many values to unpack (expected {len(elts)})"
                        if len(items) > len(elts)
                        else f"not enough values to unpack (expected {len(elts)}, got {len(items)})"
                    ),
                )
            for elt, item in zip(elts, items, strict=True):
                self._assign(elt, item)
            return
        before, after = elts[:star], elts[star + 1 :]
        if len(items) < len(before) + len(after):
            raise LearnerError(
                t(
                    "There are {have} values here, but {want} names to give them to.",
                    have=len(items),
                    want=len(before) + len(after),
                ),
                kind="type",
                exception=ValueError(
                    f"not enough values to unpack (expected at least {len(before) + len(after)},"
                    f" got {len(items)})"
                ),
            )
        for elt, item in zip(before, items, strict=False):
            self._assign(elt, item)
        rest = items[len(before) : len(items) - len(after)]
        starred = elts[star]
        assert isinstance(starred, ir.Starred)
        self._assign(starred.value, rest)
        for elt, item in zip(after, items[len(items) - len(after) :], strict=True):
            self._assign(elt, item)

    def _delete(self, target: ir.Expr) -> None:
        match target:
            case ir.Name(name=name):
                scope = self._scope_for(name)
                if name not in scope:
                    self._lookup(name)  # the friendly "I don't know" error
                    raise LearnerError(
                        t("`{name}` can't be deleted here.", name=name), kind="unknown_name"
                    )
                del scope[name]
            case ir.Subscript(value=container, index=index):
                obj = self._eval(container)
                if isinstance(obj, list | dict) and not isinstance(index, ir.Slice):
                    key = self._eval(index)
                    self._get_item(obj, key)  # same errors as reading it
                    del obj[key]
                elif isinstance(obj, list):
                    del obj[self._slice(index)]
                else:
                    raise LearnerError(
                        t("You can't delete parts of {what}.", what=describe(obj)),
                        kind="type",
                        exception=TypeError("object doesn't support item deletion"),
                    )
            case ir.Tuple(elts=elts):
                for elt in elts:
                    self._delete(elt)
            case _:
                raise LearnerError(t("You can't delete that."), kind="type")

    def _aug_assign(self, stmt: ir.AugAssign, target: ir.Expr, op: str, value: ir.Expr) -> None:
        if isinstance(target, ir.Subscript):
            container = self._eval(target.value)
            key = (
                self._slice(target.index)
                if isinstance(target.index, ir.Slice)
                else (self._eval(target.index))
            )
            old = self._get_item(container, key)
            result = self._in_place(op, old, self._eval(value))
            self._set_value(container, key, result)
            self._step(stmt, note=self._note(target, result))
            return
        assert isinstance(target, ir.Name)
        name = target.name
        scope = self._scope_for(name)
        if name not in scope:
            frame = self._frame()
            outside = frame is not None and any(name in s for s in (frame.globals, *frame.closures))
            if outside:
                raise LearnerError(
                    t(
                        "`{name}` is used in `{function}` before it gets a value there. "
                        "To change the `{name}` outside, write `global {name}` first.",
                        name=name,
                        function=frame.name if frame else "",
                    ),
                    kind="unknown_name",
                    exception=NameError(f"cannot access local variable '{name}'"),
                )
            raise LearnerError(
                t(
                    "`{name}` has no value yet, so it can't change. "
                    "Set it first, like `{name} = 0`.",
                    name=name,
                ),
                kind="unknown_name",
                exception=NameError(f"name '{name}' is not defined"),
            )
        result = self._in_place(op, scope[name], self._eval(value))
        scope[name] = result
        self._step(stmt, note=self._note(target, result))

    def _in_place(self, op: str, left: Any, right: Any) -> Any:
        """``+=`` and ``*=`` change a list itself, like in Python; others make a new value."""
        if isinstance(left, list) and op == "+":
            if not self._iterable(right):
                return self._binop(op, left, right)  # the usual friendly error
            self._guard_growth(len(left) + self._size(right))
            left += right
            return left
        if isinstance(left, list) and op == "*" and isinstance(right, int):
            self._guard_growth(len(left) * max(right, 0))
            left *= right
            return left
        if isinstance(left, set | dict) and op in ("|", "&", "-", "^"):
            result = self._binop(op, left, right)
            if isinstance(result, set) and isinstance(left, set):
                left.clear()
                left.update(result)
                return left
            if isinstance(result, dict) and isinstance(left, dict):
                left.clear()
                left.update(result)
                return left
        return self._binop(op, left, right)

    @staticmethod
    def _size(value: Any) -> int:
        try:
            return len(value)
        except TypeError:
            return 0

    def _guard_growth(self, size: int) -> None:
        if size > MAX_ITEMS:
            raise _too_many_items()

    # --- functions ---------------------------------------------------------------

    def _define(self, stmt: ir.FunctionDef) -> None:
        defaults = [
            _NO_DEFAULT if p.default is None else self._eval(p.default) for p in stmt.params
        ]
        frame = self._frame()
        closures = [] if frame is None else [frame.locals, *frame.closures]
        globals_ = frame.globals if frame else self.globals
        fn = function(self, stmt, defaults, globals_, closures)
        self._scope_for(stmt.name)[stmt.name] = fn
        params = ", ".join(p.name for p in stmt.params)
        self._step(stmt, note=f"def {stmt.name}({params})")

    def invoke(self, fn: function, args: list[Any], kwargs: dict[str, Any]) -> Any:
        """Call a learner function: bind its inputs, run its body on a new frame."""
        depth = sum(1 for f in self.frames if not f.comprehension)
        if depth >= MAX_DEPTH:
            raise LearnerError(
                t(
                    "`{name}` called itself too many times ({count} deep). "
                    "Does it have a base case that stops it?",
                    name=fn.name,
                    count=MAX_DEPTH,
                ),
                kind="too_deep",
            )
        node = fn.node
        names = [p.name for p in node.params]
        if len(args) > len(names):
            raise self._input_error(
                fn,
                t(
                    "`{name}` takes {count} input(s), but got {got}.",
                    name=fn.name,
                    count=len(names),
                    got=len(args),
                ),
            )
        bound: dict[str, Any] = dict(zip(names, args, strict=False))
        for key, value in kwargs.items():
            if key not in names:
                raise self._input_error(
                    fn, t("`{name}` has no input called `{key}`.", name=fn.name, key=key)
                )
            if key in bound:
                raise self._input_error(fn, t("`{name}` got `{key}` twice.", name=fn.name, key=key))
            bound[key] = value
        for name, default in zip(names, fn.defaults, strict=True):
            if name not in bound:
                if default is _NO_DEFAULT:
                    raise self._input_error(
                        fn, t("`{name}` needs the input `{key}`.", name=fn.name, key=name)
                    )
                bound[name] = default
        local_names = set(names) | assigned_names(node.body)
        globals_declared = global_names(node.body)
        frame = Frame(
            fn.name,
            bound,
            local_names - globals_declared,
            globals_declared,
            fn.globals,
            fn.closures,
        )
        self.frames.append(frame)
        self.events.append(
            {
                "type": "call",
                "name": fn.name,
                "args": [_short(bound[n]) for n in names],
                "depth": depth + 1,
            }
        )
        result: Any = None
        try:
            self._step(node, note=f"{fn.name}({', '.join(_short(bound[n]) for n in names)})")
            try:
                self._body(node.body)
            except _Return as returned:
                result = returned.value
            except (_Break, _Continue) as signal:
                word = "break" if isinstance(signal, _Break) else "continue"
                raise LearnerError(
                    t("`{word}` only works inside a loop.", word=word), frame.current
                ) from None
        finally:
            self.frames.pop()
        self.events.append(
            {"type": "return", "name": fn.name, "value": _short(result), "depth": depth + 1}
        )
        return result

    def _input_error(self, fn: function, message: str) -> LearnerError:
        return LearnerError(message, kind="type", exception=TypeError(message))

    # --- errors --------------------------------------------------------------------

    def _try(self, stmt: ir.Try) -> None:
        self._step(stmt)
        try:
            try:
                self._body(stmt.body)
            except LearnerError as error:
                if error.exception is None:
                    raise
                handler = self._handler_for(stmt, error.exception)
                if handler is None:
                    raise
                self._step(handler, note=type(error.exception).__name__)
                scope = self._scope_for(handler.name) if handler.name else None
                if handler.name and scope is not None:
                    scope[handler.name] = error.exception
                self.handling.append(error)
                try:
                    self._body(handler.body)
                finally:
                    self.handling.pop()
                    if handler.name and scope is not None:
                        scope.pop(handler.name, None)
            else:
                self._body(stmt.orelse)
        finally:
            if stmt.finalbody:
                self._body(stmt.finalbody)

    def _handler_for(self, stmt: ir.Try, error: BaseException) -> ir.ExceptHandler | None:
        for handler in stmt.handlers:
            if handler.kind is None:
                return handler
            kinds = self._eval(handler.kind)
            options = kinds if isinstance(kinds, tuple) else (kinds,)
            for kind in options:
                if not (isinstance(kind, type) and issubclass(kind, BaseException)):
                    raise LearnerError(
                        t(
                            "`except` needs the name of an error, like `ValueError`, not {what}.",
                            what=describe(kind),
                        ),
                        handler.id,
                        kind="type",
                    )
            if isinstance(error, options):
                return handler
        return None

    def _raise(self, exc: ir.Expr | None) -> None:
        if exc is None:
            if not self.handling:
                raise LearnerError(
                    t("A bare `raise` only works inside `except`."),
                    kind="raised",
                    exception=RuntimeError("No active exception to reraise"),
                )
            again = self.handling[-1]
            raise LearnerError(again.message, kind=again.kind, exception=again.exception)
        value = self._eval(exc)
        if isinstance(value, type) and issubclass(value, BaseException):
            value = value()
        if not isinstance(value, BaseException):
            raise LearnerError(
                t(
                    '`raise` needs an error, like `ValueError("too short")`, not {what}.',
                    what=describe(value),
                ),
                kind="type",
                exception=TypeError("exceptions must derive from BaseException"),
            )
        detail = str(value)
        raise LearnerError(
            t("`{kind}` happened: {why}", kind=type(value).__name__, why=detail)
            if detail
            else t("`{kind}` happened.", kind=type(value).__name__),
            kind="raised",
            exception=value,
        )

    # --- imports --------------------------------------------------------------------

    def _import(self, stmt: ir.Import) -> None:
        loaded = self._load_module(stmt.module)
        if not stmt.names:
            self._scope_for(stmt.module)[stmt.module] = loaded
            return
        for name in stmt.names:
            if name not in loaded.names:
                raise LearnerError(
                    t("`{module}` has no `{name}` in it.", module=stmt.module, name=name),
                    kind="unknown_name",
                    exception=ImportError(f"cannot import name '{name}' from '{stmt.module}'"),
                )
            self._scope_for(name)[name] = loaded.names[name]

    def _load_module(self, name: str) -> module:
        if name in self.loaded:
            return self.loaded[name]
        source = self.modules_source.get(name)
        if source is None:
            raise LearnerError(
                t(
                    "There is no helper file called `{name}.py` here.",
                    name=name,
                ),
                kind="unknown_name",
                exception=ModuleNotFoundError(f"No module named '{name}'"),
            )
        program = source if isinstance(source, ir.Program) else self._parse_module(name, source)
        namespace: dict[str, Any] = {}
        result = module(name, namespace)
        self.loaded[name] = result  # before running it, so a loop of imports stops
        outer, saved_frames = self.globals, self.frames
        self.globals, self.frames = namespace, []
        try:
            self._body(program.body)
        finally:
            self.globals, self.frames = outer, saved_frames
        return result

    def _parse_module(self, name: str, source: str) -> ir.Program:
        from mse_codezoo.lang_python import parse

        parsed = parse(source, id_prefix=f"{name}:")
        if not parsed.ok or parsed.program is None:
            why = parsed.errors[0].message if parsed.errors else ""
            raise LearnerError(
                t("Python can't read `{name}.py`: {why}", name=name, why=why), kind="syntax"
            )
        return parsed.program

    # --- expressions -------------------------------------------------------

    def _eval(self, expr: ir.Expr) -> Any:
        match expr:
            case ir.Const(value=value):
                return value
            case ir.Name(name=name):
                return self._lookup(name)
            case ir.Call(func=func, args=args, keywords=keywords):
                return self._call(func, args, keywords)
            case ir.MethodCall(obj=obj, method=method, args=args, keywords=keywords):
                return self._method_call(self._eval(obj), method, args, keywords)
            case ir.Attribute(value=value, attr=attr):
                return self._attribute(self._eval(value), attr)
            case ir.BinOp(op=op, left=left, right=right):
                return self._binop(op, self._eval(left), self._eval(right))
            case ir.UnaryOp(op="not", operand=operand):
                return not self._test(operand)
            case ir.UnaryOp(op=op, operand=operand):
                value = self._eval(operand)
                if isinstance(value, bool) or not isinstance(value, int | float):
                    message = t(
                        "`{op}` only works on numbers, not {what}.", op=op, what=describe(value)
                    )
                    raise LearnerError(message, kind="type", exception=TypeError(message))
                return -value if op == "-" else +value
            case ir.Compare(left=left, ops=ops, comparators=comparators):
                value = self._eval(left)
                for op, right in zip(ops, comparators, strict=True):
                    other = self._eval(right)
                    if not self._compare(op, value, other):
                        return False
                    value = other
                return True
            case ir.BoolOp(op=op, values=values):
                result: Any = None
                for item in values:
                    result = self._eval(item)
                    if self._truth(result, item) == (op == "or"):
                        return result
                return result
            case ir.IfExp(test=test, body=body, orelse=orelse):
                return self._eval(body if self._test(test) else orelse)
            case ir.FString(parts=parts):
                return self._checked("".join(self._fpart(part) for part in parts))
            case ir.Subscript(value=value, index=index):
                return self._subscript(self._eval(value), index)
            case ir.List(elts=elts):
                return self._checked(self._elements(elts))
            case ir.Tuple(elts=elts):
                return self._checked(tuple(self._elements(elts)))
            case ir.Set(elts=elts):
                return self._checked(self._hashed(set, self._elements(elts)))
            case ir.Dict(keys=keys, values=values):
                return self._dict(keys, values)
            case ir.Comprehension():
                return self._comprehension(expr)
            case ir.Starred():
                raise LearnerError(t("`*` only works inside a list or when splitting values."))
        raise LearnerError(t("CodeZoo can't work out `{what}` yet.", what=type(expr).__name__))

    def _elements(self, elts: list[ir.Expr]) -> list[Any]:
        out: list[Any] = []
        for elt in elts:
            if isinstance(elt, ir.Starred):
                value = self._eval(elt.value)
                if not self._iterable(value):
                    message = t(
                        "`*` needs something with items in it, not {what}.", what=describe(value)
                    )
                    raise LearnerError(message, kind="type", exception=TypeError(message))
                self._guard_range(value)
                out.extend(value)
            else:
                out.append(self._eval(elt))
            self._guard_growth(len(out))
        return out

    def _hashed(self, make: Callable[[list[Any]], Any], items: list[Any]) -> Any:
        try:
            return make(items)
        except TypeError as exc:
            raise LearnerError(
                t("Lists and dictionaries can't go inside a set or be a dictionary key."),
                kind="type",
                exception=exc,
            ) from None

    def _dict(self, keys: list[ir.Expr | None], values: list[ir.Expr]) -> dict[Any, Any]:
        result: dict[Any, Any] = {}
        for key, value in zip(keys, values, strict=True):
            if key is None:
                other = self._eval(value)
                if not isinstance(other, dict):
                    message = t("`**` needs a dictionary, not {what}.", what=describe(other))
                    raise LearnerError(message, kind="type", exception=TypeError(message))
                result.update(other)
            else:
                k = self._eval(key)
                self._hashed(
                    lambda items: result.__setitem__(items[0], items[1]), [k, self._eval(value)]
                )
            self._guard_growth(len(result))
        return result

    def _comprehension(self, expr: ir.Comprehension) -> Any:
        outer = self._frame()
        frame = Frame(
            "<comprehension>",
            {},
            set(),
            set(outer.global_names) if outer else set(),
            outer.globals if outer else self.globals,
            (
                [outer.locals, *outer.closures]
                if outer and not outer.comprehension
                else [outer.locals, *outer.closures]
                if outer
                else []
            ),
            comprehension=True,
        )
        for gen in expr.generators:
            frame.local_names |= assigned_names(
                [ir.Assign(target=gen.target, value=ir.Const(value=None))]
            )
        items: list[Any] = []
        pairs: list[tuple[Any, Any]] = []

        def loop(level: int) -> None:
            if level == len(expr.generators):
                if expr.kind == "dict":
                    assert expr.value is not None
                    pairs.append((self._eval(expr.elt), self._eval(expr.value)))
                else:
                    items.append(self._eval(expr.elt))
                self._guard_growth(len(items) + len(pairs))
                return
            gen = expr.generators[level]
            values = self._eval(gen.iter)
            if not self._iterable(values):
                message = t(
                    "A `for` loop needs something to go through, like `range(5)`, not {what}.",
                    what=describe(values),
                )
                raise LearnerError(message, kind="type", exception=TypeError(message))
            for value in values:
                self._tick(expr)
                self._assign(gen.target, value)
                if all(self._test(condition) for condition in gen.ifs):
                    loop(level + 1)

        # the first loop's values are worked out outside the comprehension, like Python
        self.frames.append(frame)
        try:
            loop(0)
        finally:
            self.frames.pop()
        if expr.kind == "list":
            return items
        if expr.kind == "set":
            return self._hashed(set, items)
        result: dict[Any, Any] = {}
        for key, value in pairs:
            self._hashed(lambda kv: result.__setitem__(kv[0], kv[1]), [key, value])
        return result

    def _truth(self, value: Any, expr: ir.Expr) -> bool:
        if callable(value) and not isinstance(value, type) and isinstance(expr, ir.Name):
            return self._test(expr)  # raises the friendly "add brackets" message
        return bool(value)

    def _guard_range(self, value: Any) -> None:
        # list(range(10**9)) or sum(range(10**12)) would loop inside Python, uncounted
        if isinstance(value, range) and len(value) > MAX_ITEMS:
            raise _too_many_items()

    def _keywords(self, keywords: list[ir.Keyword]) -> dict[str, Any]:
        named: dict[str, Any] = {}
        for keyword in keywords:
            named[keyword.name] = self._eval(keyword.value)
        return named

    def _call(self, func: str, args: list[ir.Expr], keywords: list[ir.Keyword]) -> Any:
        command = self._lookup(func)
        if not callable(command) or isinstance(command, range):
            message = t("`{name}` is {what}, not a command.", name=func, what=describe(command))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        values = self._elements(args)
        named = self._keywords(keywords)
        if isinstance(command, function):
            return self.invoke(command, values, named)
        return self._call_builtin(func, command, values, named)

    def _call_builtin(
        self, func: str, command: Callable[..., Any], values: list[Any], named: dict[str, Any]
    ) -> Any:
        builtin_name = next((n for n, b in self.builtins.items() if b is command), None)
        allowed = BUILTIN_KEYWORDS.get(builtin_name or "", ())
        if builtin_name == "dict":
            allowed = tuple(named)
        for key in named:
            if key not in allowed:
                raise LearnerError(
                    t("`{name}` doesn't take a named input `{key}=`.", name=func, key=key),
                    kind="type",
                    exception=TypeError(f"{func}() got an unexpected keyword argument '{key}'"),
                )
        if builtin_name in CONSUMING and not (builtin_name in ("min", "max") and not named):
            for value in values:
                self._guard_range(value)
        try:
            result = command(*values, **named)
        except LearnerError:
            raise
        except (TypeError, ValueError, OverflowError, KeyError, IndexError) as exc:
            raise LearnerError(
                t("`{name}` can't use these inputs: {why}.", name=func, why=exc),
                kind="type",
                exception=exc,
            ) from None
        except RecursionError:
            raise LearnerError(
                t("Your program went too deep for the zoo to follow."), kind="too_deep"
            ) from None
        return self._checked(result)

    def _attribute(self, obj: Any, attr: str) -> Any:
        if isinstance(obj, module):
            if attr not in obj.names:
                raise LearnerError(
                    t("`{module}` has no `{name}` in it.", module=obj.name, name=attr),
                    kind="unknown_name",
                    exception=AttributeError(f"module '{obj.name}' has no attribute '{attr}'"),
                )
            return obj.names[attr]
        if isinstance(obj, BaseException) and attr == "args":
            return obj.args
        if attr == "__name__" and isinstance(obj, type | function | module):
            return obj.name if isinstance(obj, function | module) else obj.__name__
        message = (
            t("`.{name}` needs brackets to work: `.{name}()`.", name=attr)
            if attr in self._methods_for(obj)
            else t("{what} has no `.{name}`.", what=describe(obj).capitalize(), name=attr)
        )
        raise LearnerError(
            message,
            kind="unknown_name",
            exception=AttributeError(f"'{type(obj).__name__}' object has no attribute '{attr}'"),
        )

    @staticmethod
    def _methods_for(obj: Any) -> tuple[str, ...]:
        if isinstance(obj, bool):
            return ()
        if isinstance(obj, str):
            return STR_METHODS
        if isinstance(obj, float):
            return FLOAT_METHODS
        if isinstance(obj, list):
            return LIST_METHODS
        if isinstance(obj, tuple):
            return TUPLE_METHODS
        if isinstance(obj, dict):
            return DICT_METHODS
        if isinstance(obj, set):
            return SET_METHODS
        return ()

    def _method_call(
        self, obj: Any, method: str, args: list[ir.Expr], keywords: list[ir.Keyword]
    ) -> Any:
        if isinstance(obj, module):
            command = self._attribute(obj, method)
            if not callable(command):
                message = t(
                    "`{name}` is {what}, not a command.", name=method, what=describe(command)
                )
                raise LearnerError(message, kind="type", exception=TypeError(message))
            values = self._elements(args)
            named = self._keywords(keywords)
            if isinstance(command, function):
                return self.invoke(command, values, named)
            return self._call_builtin(method, command, values, named)
        return self._method(obj, method, self._elements(args), self._keywords(keywords))

    def _method(
        self, obj: Any, method: str, args: list[Any], named: dict[str, Any] | None = None
    ) -> Any:
        named = named or {}
        allowed = self._methods_for(obj)
        if method not in allowed:
            close = difflib.get_close_matches(method, allowed, n=1)
            hint = t(" Did you mean `{name}`?", name=f".{close[0]}()") if close else ""
            raise LearnerError(
                t(
                    "{what} has no `.{method}()` command.{hint}",
                    what=describe(obj).capitalize(),
                    method=method,
                    hint=hint,
                ),
                kind="unknown_name",
                exception=AttributeError(
                    f"'{type(obj).__name__}' object has no attribute '{method}'"
                ),
            )
        for key in named:
            if key not in METHOD_KEYWORDS.get(method, ()):
                raise LearnerError(
                    t("`.{method}()` doesn't take a named input `{key}=`.", method=method, key=key),
                    kind="type",
                    exception=TypeError(f"unexpected keyword argument '{key}'"),
                )
        if isinstance(obj, str):
            if method in PAD_METHODS and args and isinstance(args[0], int) and args[0] > MAX_TEXT:
                raise _too_long()
            if method == "replace" and len(args) >= 2 and isinstance(args[1], str):
                if len(obj) * max(1, len(args[1])) > MAX_TEXT * 10:
                    raise _too_long()
            if method == "format":
                self._check_format(obj)
        if method in GROWING_METHODS and isinstance(obj, list | dict | set):
            for arg in args:
                self._guard_range(arg)
            extra = (
                sum(self._size(a) for a in args) if method in ("extend", "update", "union") else 1
            )
            self._guard_growth(len(obj) + extra)
        if method == "join":
            for arg in args:
                self._guard_range(arg)
        try:
            result = getattr(obj, method)(*args, **named)
        except LearnerError:
            raise
        except KeyError as exc:
            raise self._key_error(obj, exc.args[0] if exc.args else None) from None
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            raise LearnerError(
                t("`.{method}()` can't use these inputs: {why}.", method=method, why=exc),
                kind="type",
                exception=exc,
            ) from None
        return self._checked(result)

    def _check_format(self, template: str) -> None:
        """``.format()`` may only fill ``{}`` or ``{0}``; no ``{0.attr}`` or ``{0[key]}``."""
        try:
            parsed = list(string.Formatter().parse(template))
        except ValueError as exc:
            raise LearnerError(
                t("`.{method}()` can't use these inputs: {why}.", method="format", why=exc),
                kind="type",
                exception=exc,
            ) from None
        for _text, name, spec, _conversion in parsed:
            if name is None:
                continue
            if name and not name.isdigit():
                raise LearnerError(
                    t("In CodeZoo, `.format()` fills only `{}` or numbered `{0}` gaps."),
                    kind="type",
                )
            if spec:
                if "{" in spec:
                    raise LearnerError(
                        t("In CodeZoo, `.format()` fills only `{}` or numbered `{0}` gaps."),
                        kind="type",
                    )
                _check_spec(spec)

    def _fpart(self, part: ir.Expr) -> str:
        if isinstance(part, ir.Const):
            return str(part.value)
        assert isinstance(part, ir.FormattedValue)
        value = self._eval(part.value)
        if part.conversion == "r":
            value = repr(value)
        elif part.conversion == "s":
            value = str(value)
        elif part.conversion == "a":
            value = ascii(value)
        spec = part.spec or ""
        _check_spec(spec)
        try:
            return format(value, spec)
        except (TypeError, ValueError) as exc:
            raise LearnerError(
                t(
                    "The f-string can't show {what} like that: {why}.",
                    what=describe(value),
                    why=exc,
                ),
                kind="type",
                exception=exc,
            ) from None

    # --- [ ] -------------------------------------------------------------------------

    def _slice(self, index: ir.Expr) -> slice:
        assert isinstance(index, ir.Slice)
        bounds = [
            None if p is None else self._eval(p) for p in (index.lower, index.upper, index.step)
        ]
        for bound in bounds:
            if bound is not None and (isinstance(bound, bool) or not isinstance(bound, int)):
                message = t(
                    "Positions in `[ ]` are whole numbers, not {what}.", what=describe(bound)
                )
                raise LearnerError(message, kind="type", exception=TypeError(message))
        if bounds[2] == 0:
            raise LearnerError(
                t("A slice can't step by 0."),
                kind="type",
                exception=ValueError("slice step cannot be zero"),
            )
        return slice(*bounds)

    def _subscript(self, value: Any, index: ir.Expr) -> Any:
        if isinstance(index, ir.Slice):
            if not isinstance(value, str | range | list | tuple):
                message = t("You can't take parts of {what} with `[ ]`.", what=describe(value))
                raise LearnerError(message, kind="type", exception=TypeError(message))
            return value[self._slice(index)]
        return self._get_item(value, self._eval(index))

    def _get_item(self, value: Any, key: Any) -> Any:
        if isinstance(key, slice):
            return value[key]
        if isinstance(value, dict):
            try:
                return value[key]
            except KeyError:
                raise self._key_error(value, key) from None
            except TypeError as exc:
                raise LearnerError(
                    t("Lists and dictionaries can't go inside a set or be a dictionary key."),
                    kind="type",
                    exception=exc,
                ) from None
        if not isinstance(value, str | range | list | tuple):
            message = t("You can't take parts of {what} with `[ ]`.", what=describe(value))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        if isinstance(key, bool) or not isinstance(key, int):
            message = t("Positions in `[ ]` are whole numbers, not {what}.", what=describe(key))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        try:
            return value[key]
        except IndexError as exc:
            raise LearnerError(
                t(
                    "{what} has no position {index}: it has {count}, numbered 0 to {last}.",
                    what=repr(value) if isinstance(value, str) else describe(value).capitalize(),
                    index=key,
                    count=len(value),
                    last=len(value) - 1,
                ),
                kind="type",
                exception=exc,
            ) from None

    def _key_error(self, value: Any, key: Any) -> LearnerError:
        keys = ", ".join(repr(k) for k in list(value)[:5]) if isinstance(value, dict) else ""
        return LearnerError(
            t("The dictionary has no key {key}. Its keys are: {keys}.", key=repr(key), keys=keys)
            if keys
            else t("The dictionary has no key {key}; it is empty.", key=repr(key)),
            kind="key",
            exception=KeyError(key),
        )

    def _set_item(self, container: Any, index: ir.Expr, value: Any) -> None:
        key = self._slice(index) if isinstance(index, ir.Slice) else self._eval(index)
        self._set_value(container, key, value)

    def _set_value(self, container: Any, key: Any, value: Any) -> None:
        if isinstance(container, dict):
            self._hashed(lambda kv: container.__setitem__(kv[0], kv[1]), [key, value])
            self._guard_growth(len(container))
            return
        if isinstance(container, list):
            if isinstance(key, slice):
                if not self._iterable(value):
                    message = t("A slice can only be replaced by a list of things.")
                    raise LearnerError(message, kind="type", exception=TypeError(message))
                self._guard_range(value)
                container[key] = value
                self._guard_growth(len(container))
                return
            self._get_item(container, key)  # same checks and messages as reading it
            container[key] = value
            return
        if isinstance(container, str | tuple):
            message = t(
                "{what} can't be changed in place; make a new one instead.",
                what=describe(container).capitalize(),
            )
            raise LearnerError(
                message,
                kind="type",
                exception=TypeError(
                    f"'{type(container).__name__}' object does not support item assignment"
                ),
            )
        message = t("You can't put things into {what} with `[ ]`.", what=describe(container))
        raise LearnerError(message, kind="type", exception=TypeError(message))

    # --- operators ---------------------------------------------------------------------

    def _compare(self, op: str, left: Any, right: Any) -> bool:
        try:
            match op:
                case "==":
                    return left == right
                case "!=":
                    return left != right
                case "<":
                    return left < right
                case "<=":
                    return left <= right
                case ">":
                    return left > right
                case ">=":
                    return left >= right
                case "is":
                    return left is right
                case "is not":
                    return left is not right
                case "in":
                    return left in right
                case "not in":
                    return left not in right
        except TypeError as exc:
            raise LearnerError(
                t(
                    "`{op}` can't compare {left} and {right}.",
                    op=op,
                    left=describe(left),
                    right=describe(right),
                ),
                kind="type",
                exception=exc,
            ) from None
        raise LearnerError(t("CodeZoo doesn't know the `{op}` operator yet.", op=op))

    def _binop(self, op: str, left: Any, right: Any) -> Any:
        if op == "%" and isinstance(left, str):
            raise LearnerError(
                t("`%` with text isn't part of CodeZoo; use an f-string instead."), kind="type"
            )
        if op == "*":
            seq, times = (left, right) if isinstance(left, str | list | tuple) else (right, left)
            if isinstance(seq, str | list | tuple) and isinstance(times, int):
                limit = MAX_TEXT if isinstance(seq, str) else MAX_ITEMS
                if len(seq) * times > limit:
                    raise _too_long() if isinstance(seq, str) else _too_many_items()
        if op == "+" and isinstance(left, list | tuple) and isinstance(right, list | tuple):
            self._guard_growth(len(left) + len(right))
        if op == "**" and isinstance(left, int) and isinstance(right, int) and right > 0:
            if abs(left) > 1 and right * math.log2(abs(left)) > MAX_INT_BITS:
                raise LearnerError(t("That number is too big for the zoo."))
        try:
            match op:
                case "+":
                    result = left + right
                case "-":
                    result = left - right
                case "*":
                    result = left * right
                case "/":
                    result = left / right
                case "//":
                    result = left // right
                case "%":
                    result = left % right
                case "**":
                    result = left**right
                case "|":
                    result = left | right
                case "&":
                    result = left & right
                case "^":
                    result = left ^ right
                case _:
                    raise LearnerError(t("CodeZoo doesn't know the `{op}` operator yet.", op=op))
        except ZeroDivisionError as exc:
            raise LearnerError(t("You can't divide by zero."), kind="type", exception=exc) from None
        except OverflowError:
            raise LearnerError(t("That number is too big for the zoo.")) from None
        except TypeError as exc:
            raise LearnerError(
                t(
                    "`{op}` can't combine {left} and {right}.",
                    op=op,
                    left=describe(left),
                    right=describe(right),
                ),
                kind="type",
                exception=exc,
            ) from None
        if isinstance(result, complex):  # (-8) ** 0.5
            raise LearnerError(t("That number is too big for the zoo."))
        return self._checked(result)

    def _checked(self, value: Any) -> Any:
        if isinstance(value, str) and len(value) > MAX_TEXT:
            raise _too_long()
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= MAX_INT:
            raise LearnerError(t("That number is too big for the zoo."))
        if isinstance(value, list | tuple | set | dict) and len(value) > MAX_ITEMS:
            raise _too_many_items()
        return value

    def _print(self, *args: Any, sep: Any = " ", end: Any = "\n") -> None:
        for name, value in (("sep", sep), ("end", end)):
            if value is not None and not isinstance(value, str):
                message = t("`{key}=` needs text, not {what}.", key=name, what=describe(value))
                raise LearnerError(message, kind="type", exception=TypeError(message))
        sep = " " if sep is None else sep
        end = "\n" if end is None else end
        try:
            text = self._partial + sep.join(str(arg) for arg in args) + end
        except RecursionError:
            raise LearnerError(
                t("Your program went too deep for the zoo to follow."), kind="too_deep"
            ) from None
        self._checked(text)
        *lines, self._partial = text.split("\n")
        self.output.extend(lines)
        if sum(len(line) for line in self.output) > MAX_TEXT * 10:
            raise _too_long()


def run(
    program: ir.Program,
    actions: dict[str, Callable[..., Any]] | None = None,
    drain_events: Callable[[], list[dict[str, Any]]] | None = None,
    max_steps: int = MAX_STEPS,
    on_step: Callable[[Step], None] | None = None,
    modules: dict[str, str | ir.Program] | None = None,
) -> RunResult:
    """Run to the end and collect every step."""
    runner = Runner(program, actions, drain_events, max_steps, modules=modules, on_step=on_step)
    runner.execute()
    return RunResult(runner.steps, runner.output, runner.error)
