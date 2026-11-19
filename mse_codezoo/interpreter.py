"""Step-by-step evaluator for the IR.

Each statement yields a ``Step`` so clients can highlight the block and line and animate
the world. Learner code never reaches ``exec`` or ``eval``: only the builtins and text
methods listed here and the world actions passed in exist. Standard library only.
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
MAX_INT = 10**100
MAX_INT_BITS = MAX_INT.bit_length()

# Text methods learners may call; everything else on a value is unknown.
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
)
FLOAT_METHODS = ("is_integer",)
PAD_METHODS = ("center", "ljust", "rjust", "zfill")
PRINT_KEYWORDS = ("sep", "end")
NUMBER_IN_SPEC = re.compile(r"\d+")


class LearnerError(Exception):
    """A problem in the learner's program, worded for the learner.

    ``kind`` sorts mistakes for the grown-up report: ``bump``, ``unknown_name``,
    ``too_many_steps``, ``type`` or ``other``.
    """

    def __init__(self, message: str, node_id: str | None = None, kind: str = "other") -> None:
        super().__init__(message)
        self.message = message
        self.node_id = node_id
        self.kind = kind


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
    if isinstance(value, type):
        return t("a type")
    if callable(value):
        return t("a command")
    return type(value).__name__


def _range(*args: Any) -> range:
    return range(*args)


def _extreme(pick: Callable[..., Any], *args: Any) -> Any:
    # min/max over a huge range would loop inside Python without counting steps
    if len(args) == 1 and isinstance(args[0], range):
        values = args[0]
        if not values:
            raise ValueError("the range is empty")
        return pick(values[0], values[-1])
    return pick(*args)


def _type(value: Any) -> type:
    return type(value)


def _check_spec(spec: str) -> None:
    """Refuse format specs that would build enormous text, like ``:>999999999``."""
    for number in NUMBER_IN_SPEC.findall(spec):
        if int(number) > MAX_TEXT:
            raise LearnerError(t("That text would be far too long for the zoo."))


class Runner:
    """Runs one program. Iterate ``steps()``; afterwards read ``output`` and ``error``."""

    def __init__(
        self,
        program: ir.Program,
        actions: dict[str, Callable[..., Any]] | None = None,
        drain_events: Callable[[], list[dict[str, Any]]] | None = None,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self.program = program
        self.actions = dict(actions or {})
        self.drain = drain_events or list
        self.max_steps = max_steps
        self.env: dict[str, Any] = {}
        self.output: list[str] = []
        self._partial = ""  # printed text after the last newline
        self.count = 0
        self.error: LearnerError | None = None
        self.builtins: dict[str, Callable[..., Any]] = {
            "print": self._print,
            "range": _range,
            "len": len,
            "abs": abs,
            "min": lambda *a: _extreme(min, *a),
            "max": lambda *a: _extreme(max, *a),
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "round": round,
            "type": _type,
        }

    def steps(self) -> Iterator[Step]:
        try:
            yield from self._body(self.program.body)
        except LearnerError as exc:
            self.error = exc
            yield Step(exc.node_id or self.program.id, self.drain(), error=exc.message)
        finally:
            if self._partial:
                self.output.append(self._partial)
                self._partial = ""

    # --- statements --------------------------------------------------------

    def _body(self, stmts: list[ir.Stmt]) -> Iterator[Step]:
        for stmt in stmts:
            yield from self._stmt(stmt)

    def _stmt(self, stmt: ir.Stmt) -> Iterator[Step]:
        if isinstance(stmt, ir.Comment | ir.Pass):
            return
        try:
            self._tick(stmt)
            match stmt:
                case ir.ExprStmt(value=value):
                    self._eval(value)
                    yield Step(stmt.id, self.drain())
                case ir.Assign(target=target, value=value):
                    result = self._eval(value)
                    self.env[target.name] = result
                    yield Step(stmt.id, self.drain(), note=f"{target.name} = {result!r}")
                case ir.AugAssign(target=target, op=op, value=value):
                    if target.name not in self.env:
                        raise LearnerError(
                            t(
                                "`{name}` has no value yet, so it can't change. "
                                "Set it first, like `{name} = 0`.",
                                name=target.name,
                            ),
                            kind="unknown_name",
                        )
                    result = self._binop(op, self.env[target.name], self._eval(value))
                    self.env[target.name] = result
                    yield Step(stmt.id, self.drain(), note=f"{target.name} = {result!r}")
                case ir.For(target=target, iter=iterable, body=body):
                    values = self._eval(iterable)
                    if not isinstance(values, range | str):
                        raise LearnerError(
                            t(
                                "A `for` loop needs something to go through, like `range(5)`, "
                                "not {what}.",
                                what=describe(values),
                            ),
                            kind="type",
                        )
                    first = True
                    for item in values:
                        if not first:
                            self._tick(stmt)
                        first = False
                        self.env[target.name] = item
                        yield Step(stmt.id, self.drain(), note=f"{target.name} = {item!r}")
                        yield from self._body(body)
                case ir.If(test=test, body=body, orelse=orelse):
                    passed = self._test(test)
                    yield Step(stmt.id, self.drain(), note=f"-> {passed}")
                    yield from self._body(body if passed else orelse)
                case ir.While(test=test, body=body):
                    while True:
                        passed = self._test(test)
                        yield Step(stmt.id, self.drain(), note=f"-> {passed}")
                        if not passed:
                            break
                        yield from self._body(body)
                        self._tick(stmt)
                case ir.RawCode(reason=reason):
                    raise LearnerError(t("CodeZoo can't run {what} yet.", what=t(reason)))
                case _:
                    raise LearnerError(
                        t("CodeZoo can't run `{what}` yet.", what=type(stmt).__name__)
                    )
        except LearnerError as exc:
            if exc.node_id is None:
                exc.node_id = stmt.id
            raise

    def _tick(self, stmt: ir.Stmt) -> None:
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

    # --- expressions -------------------------------------------------------

    def _lookup(self, name: str) -> Any:
        for scope in (self.env, self.builtins, self.actions):
            if name in scope:
                return scope[name]
        # the learner's own names and the animal's commands are the likeliest typos
        close = difflib.get_close_matches(name, [*self.env, *self.actions], n=1)
        close = close or difflib.get_close_matches(name, list(self.builtins), n=1)
        hint = t(" Did you mean `{name}`?", name=close[0]) if close else ""
        raise LearnerError(
            t("I don't know `{name}`.{hint}", name=name, hint=hint), kind="unknown_name"
        )

    def _eval(self, expr: ir.Expr) -> Any:
        match expr:
            case ir.Const(value=value):
                return value
            case ir.Name(name=name):
                return self._lookup(name)
            case ir.Call(func=func, args=args, keywords=keywords):
                return self._call(func, args, keywords)
            case ir.MethodCall(obj=obj, method=method, args=args):
                return self._method(self._eval(obj), method, [self._eval(a) for a in args])
            case ir.BinOp(op=op, left=left, right=right):
                return self._binop(op, self._eval(left), self._eval(right))
            case ir.UnaryOp(op="not", operand=operand):
                return not self._test(operand)
            case ir.UnaryOp(op=op, operand=operand):
                value = self._eval(operand)
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise LearnerError(
                        t("`{op}` only works on numbers, not {what}.", op=op, what=describe(value)),
                        kind="type",
                    )
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
        raise LearnerError(t("CodeZoo can't work out `{what}` yet.", what=type(expr).__name__))

    def _truth(self, value: Any, expr: ir.Expr) -> bool:
        if callable(value) and not isinstance(value, type) and isinstance(expr, ir.Name):
            return self._test(expr)  # raises the friendly "add brackets" message
        return bool(value)

    def _call(self, func: str, args: list[ir.Expr], keywords: list[ir.Keyword]) -> Any:
        command = self._lookup(func)
        if not callable(command) or isinstance(command, range):
            raise LearnerError(
                t("`{name}` is {what}, not a command.", name=func, what=describe(command)),
                kind="type",
            )
        values = [self._eval(arg) for arg in args]
        named: dict[str, Any] = {}
        for keyword in keywords:
            if command != self._print or keyword.name not in PRINT_KEYWORDS:
                raise LearnerError(
                    t(
                        "`{name}` doesn't take a named input `{key}=`.",
                        name=func,
                        key=keyword.name,
                    ),
                    kind="type",
                )
            named[keyword.name] = self._eval(keyword.value)
        try:
            result = command(*values, **named)
        except LearnerError:
            raise
        except (TypeError, ValueError, OverflowError) as exc:
            raise LearnerError(
                t("`{name}` can't use these inputs: {why}.", name=func, why=exc), kind="type"
            ) from None
        return self._checked(result)

    def _method(self, obj: Any, method: str, args: list[Any]) -> Any:
        if isinstance(obj, str) and not isinstance(obj, bool):
            allowed = STR_METHODS
        elif isinstance(obj, float):
            allowed = FLOAT_METHODS
        else:
            allowed = ()
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
            )
        if method in PAD_METHODS and args and isinstance(args[0], int) and args[0] > MAX_TEXT:
            raise LearnerError(t("That text would be far too long for the zoo."))
        if method == "replace" and len(args) >= 2 and isinstance(args[1], str):
            if len(obj) * max(1, len(args[1])) > MAX_TEXT * 10:
                raise LearnerError(t("That text would be far too long for the zoo."))
        if method == "format":
            self._check_format(obj)
        try:
            result = getattr(obj, method)(*args)
        except (TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
            raise LearnerError(
                t("`.{method}()` can't use these inputs: {why}.", method=method, why=exc),
                kind="type",
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
            ) from None

    def _subscript(self, value: Any, index: ir.Expr) -> Any:
        if not isinstance(value, str | range):
            raise LearnerError(
                t("You can't take parts of {what} with `[ ]`.", what=describe(value)), kind="type"
            )
        if isinstance(index, ir.Slice):
            bounds = [
                None if p is None else self._eval(p) for p in (index.lower, index.upper, index.step)
            ]
            for bound in bounds:
                if bound is not None and (isinstance(bound, bool) or not isinstance(bound, int)):
                    raise LearnerError(
                        t(
                            "Positions in `[ ]` are whole numbers, not {what}.",
                            what=describe(bound),
                        ),
                        kind="type",
                    )
            if bounds[2] == 0:
                raise LearnerError(t("A slice can't step by 0."), kind="type")
            return value[slice(*bounds)]
        position = self._eval(index)
        if isinstance(position, bool) or not isinstance(position, int):
            raise LearnerError(
                t("Positions in `[ ]` are whole numbers, not {what}.", what=describe(position)),
                kind="type",
            )
        try:
            return value[position]
        except IndexError:
            raise LearnerError(
                t(
                    "{what} has no position {index}: it has {count}, numbered 0 to {last}.",
                    what=repr(value) if isinstance(value, str) else describe(value),
                    index=position,
                    count=len(value),
                    last=len(value) - 1,
                ),
                kind="type",
            ) from None

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
        except TypeError:
            raise LearnerError(
                t(
                    "`{op}` can't compare {left} and {right}.",
                    op=op,
                    left=describe(left),
                    right=describe(right),
                ),
                kind="type",
            ) from None
        raise LearnerError(t("CodeZoo doesn't know the `{op}` operator yet.", op=op))

    def _binop(self, op: str, left: Any, right: Any) -> Any:
        if op == "%" and isinstance(left, str):
            raise LearnerError(
                t("`%` with text isn't part of CodeZoo; use an f-string instead."), kind="type"
            )
        if op == "*":
            text, times = (left, right) if isinstance(left, str) else (right, left)
            if isinstance(text, str) and isinstance(times, int) and len(text) * times > MAX_TEXT:
                raise LearnerError(t("That text would be far too long for the zoo."))
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
                case _:
                    raise LearnerError(t("CodeZoo doesn't know the `{op}` operator yet.", op=op))
        except ZeroDivisionError:
            raise LearnerError(t("You can't divide by zero."), kind="type") from None
        except OverflowError:
            raise LearnerError(t("That number is too big for the zoo.")) from None
        except TypeError:
            raise LearnerError(
                t(
                    "`{op}` can't combine {left} and {right}.",
                    op=op,
                    left=describe(left),
                    right=describe(right),
                ),
                kind="type",
            ) from None
        if isinstance(result, complex):  # (-8) ** 0.5
            raise LearnerError(t("That number is too big for the zoo."))
        return self._checked(result)

    def _checked(self, value: Any) -> Any:
        if isinstance(value, str) and len(value) > MAX_TEXT:
            raise LearnerError(t("That text would be far too long for the zoo."))
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= MAX_INT:
            raise LearnerError(t("That number is too big for the zoo."))
        return value

    def _print(self, *args: Any, sep: Any = " ", end: Any = "\n") -> None:
        for name, value in (("sep", sep), ("end", end)):
            if value is not None and not isinstance(value, str):
                raise LearnerError(
                    t("`{key}=` needs text, not {what}.", key=name, what=describe(value)),
                    kind="type",
                )
        sep = " " if sep is None else sep
        end = "\n" if end is None else end
        text = self._partial + sep.join(str(arg) for arg in args) + end
        self._checked(text)
        *lines, self._partial = text.split("\n")
        self.output.extend(lines)
        if sum(len(line) for line in self.output) > MAX_TEXT * 10:
            raise LearnerError(t("That text would be far too long for the zoo."))


def run(
    program: ir.Program,
    actions: dict[str, Callable[..., Any]] | None = None,
    drain_events: Callable[[], list[dict[str, Any]]] | None = None,
    max_steps: int = MAX_STEPS,
    on_step: Callable[[Step], None] | None = None,
) -> RunResult:
    """Run to the end and collect every step."""
    runner = Runner(program, actions, drain_events, max_steps)
    steps = []
    for step in runner.steps():
        steps.append(step)
        if on_step is not None:
            on_step(step)
    return RunResult(steps, runner.output, runner.error)
