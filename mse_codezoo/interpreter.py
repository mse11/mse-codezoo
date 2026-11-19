"""Step-by-step evaluator for the IR.

Each statement yields a ``Step`` so clients can highlight the block and line and animate
the world. Learner code never reaches ``exec`` or ``eval``: only the builtins listed here
and the world actions passed in exist. Standard library only.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from mse_codezoo import ir

MAX_STEPS = 10_000
MAX_TEXT = 10_000
MAX_INT = 10**100


class LearnerError(Exception):
    """A problem in the learner's program, worded for the learner."""

    def __init__(self, message: str, node_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.node_id = node_id


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
        return "a yes/no value"
    if isinstance(value, int):
        return "a whole number"
    if isinstance(value, float):
        return "a decimal number"
    if isinstance(value, str):
        return "text"
    if value is None:
        return "nothing (`None`)"
    if isinstance(value, range):
        return "a range"
    if callable(value):
        return "a command"
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
        }

    def steps(self) -> Iterator[Step]:
        try:
            yield from self._body(self.program.body)
        except LearnerError as exc:
            self.error = exc
            yield Step(exc.node_id or self.program.id, self.drain(), error=exc.message)

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
                            f"`{target.name}` has no value yet, so it can't change. "
                            f"Set it first, like `{target.name} = 0`."
                        )
                    result = self._binop(op, self.env[target.name], self._eval(value))
                    self.env[target.name] = result
                    yield Step(stmt.id, self.drain(), note=f"{target.name} = {result!r}")
                case ir.For(target=target, iter=iterable, body=body):
                    values = self._eval(iterable)
                    if not isinstance(values, range | str):
                        raise LearnerError(
                            f"A `for` loop needs something to go through, like `range(5)`, "
                            f"not {describe(values)}."
                        )
                    first = True
                    for item in values:
                        if not first:
                            self._tick(stmt)
                        first = False
                        self.env[target.name] = item
                        yield Step(stmt.id, self.drain(), note=f"{target.name} = {item!r}")
                        yield from self._body(body)
                case ir.RawCode(reason=reason):
                    raise LearnerError(f"CodeZoo can't run {reason} yet.")
                case _:
                    raise LearnerError(f"CodeZoo can't run `{type(stmt).__name__}` yet.")
        except LearnerError as exc:
            if exc.node_id is None:
                exc.node_id = stmt.id
            raise

    def _tick(self, stmt: ir.Stmt) -> None:
        self.count += 1
        if self.count > self.max_steps:
            raise LearnerError(
                f"Your program took more than {self.max_steps} steps. "
                "Is a loop running too many times?",
                stmt.id,
            )

    # --- expressions -------------------------------------------------------

    def _lookup(self, name: str) -> Any:
        for scope in (self.env, self.builtins, self.actions):
            if name in scope:
                return scope[name]
        known = [*self.env, *self.builtins, *self.actions]
        close = difflib.get_close_matches(name, known, n=1)
        hint = f" Did you mean `{close[0]}`?" if close else ""
        raise LearnerError(f"I don't know `{name}`.{hint}")

    def _eval(self, expr: ir.Expr) -> Any:
        match expr:
            case ir.Const(value=value):
                return value
            case ir.Name(name=name):
                return self._lookup(name)
            case ir.Call(func=func, args=args):
                command = self._lookup(func)
                if not callable(command):
                    raise LearnerError(f"`{func}` is {describe(command)}, not a command.")
                values = [self._eval(arg) for arg in args]
                try:
                    result = command(*values)
                except LearnerError:
                    raise
                except (TypeError, ValueError) as exc:
                    raise LearnerError(f"`{func}` can't use these inputs: {exc}.") from None
                return self._checked(result)
            case ir.BinOp(op=op, left=left, right=right):
                return self._binop(op, self._eval(left), self._eval(right))
            case ir.UnaryOp(op=op, operand=operand):
                value = self._eval(operand)
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise LearnerError(f"`{op}` only works on numbers, not {describe(value)}.")
                return -value if op == "-" else +value
        raise LearnerError(f"CodeZoo can't work out `{type(expr).__name__}` yet.")

    def _binop(self, op: str, left: Any, right: Any) -> Any:
        if op == "%" and isinstance(left, str):
            raise LearnerError("`%` with text isn't part of CodeZoo; join text with `+` instead.")
        if op == "*":
            text, times = (left, right) if isinstance(left, str) else (right, left)
            if isinstance(text, str) and isinstance(times, int) and len(text) * times > MAX_TEXT:
                raise LearnerError("That text would be far too long for the zoo.")
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
                case _:
                    raise LearnerError(f"CodeZoo doesn't know the `{op}` operator yet.")
        except ZeroDivisionError:
            raise LearnerError("You can't divide by zero.") from None
        except TypeError:
            raise LearnerError(
                f"`{op}` can't combine {describe(left)} and {describe(right)}."
            ) from None
        return self._checked(result)

    def _checked(self, value: Any) -> Any:
        if isinstance(value, str) and len(value) > MAX_TEXT:
            raise LearnerError("That text would be far too long for the zoo.")
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= MAX_INT:
            raise LearnerError("That number is too big for the zoo.")
        return value

    def _print(self, *args: Any) -> None:
        line = " ".join(str(arg) for arg in args)
        self._checked(line)
        self.output.append(line)


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
