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
import types
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields
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
MAX_ITERATIONS = 200_000  # items handed out by map(), zip(), itertools... in one run
MAX_FILES = 20

# Special names a learner's class may define; anything else spelt `__like_this__` is
# refused, so a class can't hook into the interpreter (``__del__``, ``__getattribute__``).
CLASS_DUNDERS = (
    "__init__",
    "__post_init__",
    "__str__",
    "__repr__",
    "__eq__",
    "__ne__",
    "__lt__",
    "__le__",
    "__gt__",
    "__ge__",
    "__hash__",
    "__len__",
    "__bool__",
    "__contains__",
    "__getitem__",
    "__setitem__",
    "__iter__",
    "__next__",
    "__call__",
    "__add__",
    "__sub__",
    "__mul__",
    "__enter__",
    "__exit__",
    "__aenter__",
    "__aexit__",
    "__match_args__",
    "__slots__",
    "__doc__",
)
# ... and special names a program may read on objects
OPEN_DUNDERS = (*CLASS_DUNDERS, "__name__", "__mro__", "__dict__")
CLASS_NAMESPACE = ("__module__", "__qualname__", "__annotations__", "__codezoo__")

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
    "open": ("mode", "encoding"),
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
        AttributeError,
        StopIteration,
        EOFError,
        FileNotFoundError,
        OSError,
        NotImplementedError,
        ExceptionGroup,
        BaseExceptionGroup,
        BaseException,
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
    """One thing the program did. ``lane`` names the task or thread that did it and ``time``
    is the simulated clock, once a program runs things at the same time."""

    node_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None
    error: str | None = None
    lane: str | None = None
    time: float | None = None
    # what the variables look like after this step (only when the runner watches; see
    # ``Runner._watch``): changes since the step before, so a long run stays small
    scope: dict[str, Any] | None = None


@dataclass
class RunResult:
    steps: list[Step]
    output: list[str]
    error: LearnerError | None
    time: float = 0.0  # the simulated clock at the end (async tasks and threads)
    lanes: list[str] = field(default_factory=list)  # tasks and threads, in start order
    files: dict[str, str] = field(default_factory=dict)  # the run's files after it

    @property
    def ok(self) -> bool:
        return self.error is None


class ZooObject:
    """Something the zoo hands to programs (a lock, a task, a file). Programs may use only
    the attributes in ``ZOO_ATTRS``; ``KIND`` is how it is described to learners."""

    ZOO_ATTRS: tuple[str, ...] = ()
    KIND = "a zoo object"

    def __copy__(self) -> Any:
        return self

    def __deepcopy__(self, memo: Any) -> Any:
        return self


class Awaitable(ZooObject):
    """Something ``await`` can wait for. ``wait`` is a generator: it yields requests to the
    scheduler (``("sleep", seconds)``, ``("wait", future)``) and returns the result."""

    def wait(self, runner: Runner) -> Generator[Any, Any, Any]:
        raise NotImplementedError
        yield  # pragma: no cover


class function:  # noqa: N801 - named like Python's own, so `type(f)` shows <class 'function'>
    """A function the learner taught with ``def`` (or ``lambda``)."""

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
        self.owner: type | None = None  # the class it was taught in, for super()
        self.wrapped: Any = None  # set by functools.wraps

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # e.g. sorted(logs, key=size)
        return self.runner.invoke(self, list(args), kwargs)

    def __get__(self, obj: Any, owner: Any = None) -> Any:
        """Inside a class a function becomes a method: ``bee.work()`` passes ``bee``."""
        return self if obj is None else types.MethodType(self, obj)

    @property
    def __name__(self) -> str:  # noqa: PLW3201
        return self.name

    def __getattr__(self, attr: str) -> Any:
        if attr == "__qualname__":  # can't be a property: `type` claims that name
            return f"{self.owner.__name__}.{self.name}" if self.owner else self.name
        raise AttributeError(attr)

    @property
    def __wrapped__(self) -> Any:  # noqa: PLW3201
        if self.wrapped is None:
            raise AttributeError("__wrapped__")
        return self.wrapped

    def __copy__(self) -> Any:
        return self

    def __deepcopy__(self, memo: Any) -> Any:
        return self

    def __repr__(self) -> str:
        return f"<function {self.__qualname__}>"


function.__module__ = "builtins"


class generator(ZooObject):  # noqa: N801 - like Python's own generator type
    """What calling a generator function gives: it runs a little each time it is asked."""

    ZOO_ATTRS = ("send", "close")
    KIND = "a generator"

    def __init__(self, name: str, body: Generator[Any, Any, Any]) -> None:
        self.name = name
        self._body = body
        self.running = False
        self.finished = False

    def __iter__(self) -> generator:
        return self

    def __next__(self) -> Any:
        return self.send(None)

    def send(self, value: Any) -> Any:
        if self.finished:
            raise StopIteration
        if self.running:
            message = t("A generator can't ask itself for its next value.")
            raise LearnerError(message, kind="type", exception=ValueError(message))
        self.running = True
        try:
            return self._body.send(value)
        except BaseException:
            self.finished = True
            raise
        finally:
            self.running = False

    def close(self) -> None:
        if not self.finished and not self.running:
            self._body.close()
        self.finished = True

    def __repr__(self) -> str:
        return f"<generator object {self.name}>"


generator.__module__ = "builtins"


class coroutine(Awaitable):  # noqa: N801 - like Python's own coroutine type
    """What calling an ``async def`` gives: nothing has run yet until it is awaited."""

    KIND = "a coroutine"

    def __init__(self, name: str, label: str, body: Generator[Any, Any, Any], node_id: str):
        self.name = name
        self.label = label  # `arm(3)`: the lane's name when it runs as a task
        self._body = body
        self.started = False
        self.node_id = node_id  # where it was made, for "never awaited"

    def wait(self, runner: Runner) -> Generator[Any, Any, Any]:
        if self.started:
            raise LearnerError(
                t(
                    "This coroutine already ran. Call `{name}()` again for a new one.",
                    name=self.name,
                ),
                kind="type",
                exception=RuntimeError("cannot reuse already awaited coroutine"),
            )
        self.started = True
        return (yield from self._body)

    def __repr__(self) -> str:
        return f"<coroutine object {self.name}>"


coroutine.__module__ = "builtins"


class iterator(ZooObject):  # noqa: N801
    """A lazy iterator from ``map()``, ``zip()`` or ``itertools``; it counts what it hands
    out, so an endless one stops at the zoo's limit instead of freezing the computer."""

    KIND = "an iterator"

    def __init__(self, runner: Runner, name: str, source: Iterator[Any]) -> None:
        self.runner = runner
        self.name = name
        self._source = source

    def __iter__(self) -> iterator:
        return self

    def __next__(self) -> Any:
        self.runner.count_iteration()
        return next(self._source)

    def __repr__(self) -> str:
        return f"<{self.name} object>"


iterator.__module__ = "builtins"


class module:  # noqa: N801 - like Python's own module type
    """A helper file brought in with ``import``."""

    def __init__(self, name: str, names: dict[str, Any]) -> None:
        self.name = name
        self.names = names
        self.newer: dict[str, tuple[int, int]] = {}  # names that arrive in a later Python

    def __repr__(self) -> str:
        return f"<module '{self.name}'>"


module.__module__ = "builtins"

_NO_DEFAULT = object()


@dataclass(eq=False)
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
    function: function | None = None
    nonlocal_names: set[str] = field(default_factory=set)
    is_class: bool = False  # a class body: its names are not closures for its methods
    annotations: dict[str, str] = field(default_factory=dict)  # a class body's type hints
    resolved: dict[str, Any] = field(default_factory=dict)  # finished `await` / `yield`


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
    if isinstance(value, ZooObject):
        return t(type(value).KIND)
    if isinstance(value, type) and getattr(value, "__codezoo__", False):
        return t("the class `{name}`", name=value.__name__)
    if getattr(type(value), "__codezoo__", False):
        return t("a `{name}`", name=type(value).__name__)
    if isinstance(value, BaseException):
        return t("an error")
    if isinstance(value, type):
        return t("a type")
    if callable(value):
        return t("a command")
    return type(value).__name__


def _short(value: Any) -> str:
    text = safe_repr(value)
    return text if len(text) <= MAX_NOTE else text[: MAX_NOTE - 3] + "..."


MAX_WATCHED = 30  # variables shown per scope in the debugger
MAX_WATCH_TEXT = 60


def _watched(names: dict[str, Any]) -> dict[str, str]:
    """The learner's own variables and their values as short text, for the debugger:
    commands, functions, classes and modules are left out (they are not values a child
    tracks), and so are names starting with ``_``."""
    shown: dict[str, str] = {}
    for name, value in names.items():
        if name.startswith("_") or isinstance(value, type | types.ModuleType | module):
            continue
        if callable(value) and not getattr(type(value), "__codezoo__", False):
            continue
        text = watch_repr(value)
        shown[name] = text if len(text) <= MAX_WATCH_TEXT else text[: MAX_WATCH_TEXT - 3] + "..."
        if len(shown) >= MAX_WATCHED:
            break
    return shown


def watch_repr(value: Any) -> str:
    """Like ``safe_repr``, but an object of the learner's own class shows its attributes
    (``Dog(name='Rex', age=3)``), read straight from the object, so none of its code runs."""
    if getattr(type(value), "__codezoo__", False) and not isinstance(value, type):
        attrs = getattr(value, "__dict__", None)
        if isinstance(attrs, dict):
            inner = ", ".join(
                f"{k}={safe_repr(v, 2)}"
                for k, v in list(attrs.items())[:6]
                if not k.startswith("_")
            )
            return f"{type(value).__name__}({inner})"
    return safe_repr(value)


def safe_repr(value: Any, depth: int = 0) -> str:
    """``repr`` for notes and events, without running any of the learner's own code (a
    class's ``__repr__`` could call itself, or move the animal)."""
    if isinstance(value, type) and getattr(value, "__codezoo__", False):
        return f"<class '{value.__name__}'>"
    if getattr(type(value), "__codezoo__", False):
        return f"<{type(value).__name__} object>"
    if depth > 3:
        return "..."
    if isinstance(value, list | tuple | set | frozenset) and type(value) in (
        list,
        tuple,
        set,
        frozenset,
    ):
        items = list(value)[:12]
        inner = ", ".join(safe_repr(item, depth + 1) for item in items)
        if len(value) > len(items):
            inner += ", ..."
        if isinstance(value, list):
            return f"[{inner}]"
        if isinstance(value, tuple):
            return f"({inner},)" if len(value) == 1 else f"({inner})"
        return f"{{{inner}}}" if value else "set()"
    if type(value) is dict:
        pairs = list(value.items())[:12]
        inner = ", ".join(f"{safe_repr(k, depth + 1)}: {safe_repr(v, depth + 1)}" for k, v in pairs)
        return "{" + inner + (", ..." if len(value) > len(pairs) else "") + "}"
    if isinstance(value, BaseException) and not isinstance(value, BaseExceptionGroup):
        args = ", ".join(safe_repr(a, depth + 1) for a in value.args)
        return f"{type(value).__name__}({args})"
    if isinstance(value, types.MethodType):
        return f"<bound method {getattr(value.__func__, '__name__', '?')}>"
    return repr(value)


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

    def pattern_names(pattern: ir.Pattern) -> None:
        for node in ir.walk(pattern):
            name = getattr(node, "name", None) if isinstance(node, ir.Pattern) else None
            if isinstance(name, str):
                names.add(name)
            if isinstance(node, ir.PatternMapping) and node.rest:
                names.add(node.rest)

    def visit(body: list[ir.Stmt]) -> None:
        for stmt in body:
            match stmt:
                case ir.Assign(target=target) | ir.AugAssign(target=target):
                    targets(target)
                case ir.AnnAssign(target=target, value=value) if value is not None:
                    targets(target)
                case ir.For(target=target, body=inner):
                    targets(target)
                    visit(inner)
                case ir.Delete(targets=items):
                    for item in items:
                        targets(item)
                case ir.FunctionDef(name=name) | ir.ClassDef(name=name) | ir.TypeAlias(name=name):
                    names.add(name)  # its body has its own scope
                case ir.With(items=items, body=inner):
                    for item in items:
                        if item.target is not None:
                            targets(item.target)
                    visit(inner)
                case ir.Match(cases=cases):
                    for case in cases:
                        pattern_names(case.pattern)
                        visit(case.body)
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


def global_names(stmts: list[ir.Stmt], kind: type[ir.Stmt] = ir.Global) -> set[str]:
    """Names a body declares ``global`` (or, with ``kind=ir.Nonlocal``, ``nonlocal``)."""
    found: set[str] = set()
    for stmt in stmts:
        for inner in local_walk(stmt):
            if isinstance(inner, kind):
                found.update(inner.names)  # type: ignore[attr-defined]
    return found


def local_walk(node: ir.Node) -> Iterator[ir.Node]:
    """Like ``ir.walk``, but without the insides of functions, classes and lambdas defined
    in ``node``: those run on their own."""
    yield node
    for f in fields(node):
        value = getattr(node, f.name)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, ir.Node):
                continue
            if isinstance(item, ir.FunctionDef | ir.ClassDef | ir.Lambda):
                # decorators, defaults and bases run here; the body runs later
                for part in (*getattr(item, "decorators", []), *getattr(item, "bases", [])):
                    yield from local_walk(part)
                for param in getattr(item, "params", []):
                    if param.default is not None:
                        yield from local_walk(param.default)
                continue
            if isinstance(item, ir.Comprehension):
                yield from local_walk(item.generators[0].iter)  # the rest has its own scope
                continue
            yield from local_walk(item)


SUSPENDS = (ir.Yield, ir.YieldFrom, ir.Await)


def _suspend_order(node: ir.Node) -> list[ir.Expr]:
    """The ``await`` / ``yield`` parts of ``node`` in the order Python reaches them: left to
    right, and the inside of each before itself (``await f(await g())``: ``g`` first)."""
    found: list[ir.Expr] = []

    def visit(item: ir.Node, top: bool) -> None:
        if not top and isinstance(item, ir.FunctionDef | ir.ClassDef | ir.Lambda):
            return
        if not top and isinstance(item, ir.Comprehension):
            visit(item.generators[0].iter, False)
            return
        for f in fields(item):
            value = getattr(item, f.name)
            for part in value if isinstance(value, list) else [value]:
                if isinstance(part, ir.Node) and not isinstance(part, ir.Stmt):
                    visit(part, False)
        if isinstance(item, SUSPENDS):
            found.append(item)  # type: ignore[arg-type]

    visit(node, True)
    return found


def _functions_inside(value: Any) -> Iterator[function]:
    """Learner functions a class attribute holds: a method, or one inside ``@property``,
    ``@classmethod`` or ``@staticmethod``, so ``super()`` knows its class."""
    if isinstance(value, function):
        yield value
    elif isinstance(value, property):
        for part in (value.fget, value.fset, value.fdel):
            yield from _functions_inside(part)
    elif isinstance(value, classmethod | staticmethod):
        yield from _functions_inside(value.__func__)
    elif hasattr(value, "__wrapped__") and isinstance(value, ZooObject):
        yield from _functions_inside(value.__wrapped__)


def is_generator_body(stmts: list[ir.Stmt]) -> bool:
    return any(isinstance(n, ir.Yield | ir.YieldFrom) for s in stmts for n in local_walk(s))


class Runner:
    """Runs one program. Call ``execute()``; afterwards read ``steps``, ``output``, ``error``.

    ``modules`` maps a helper file's name (``"tricks"``) to its Python source or IR, for
    ``import tricks``. ``on_step`` sees every step as it happens. ``version`` is the Python
    release the program is written for (builtins newer than it don't exist); ``seed`` makes
    ``random`` and the thread scheduler repeat exactly; ``inputs`` are the answers
    ``input()`` gets; ``files`` is the program's little disk for ``open()`` (changed in
    place); ``gil=False`` lets threads truly run at the same time (Python 3.13+).
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
        version: tuple[int, int] | None = None,
        seed: int = 0,
        inputs: list[str] | None = None,
        files: dict[str, str] | None = None,
        gil: bool = True,
        watch: bool = False,
    ) -> None:
        import random

        from mse_codezoo.versions import DEFAULT

        self.program = program
        self.actions = dict(actions or {})
        self.drain_world = drain_events or list
        self.max_steps = max_steps
        self.modules_source = dict(modules or {})
        self.loaded: dict[str, module] = {}
        self.on_step = on_step
        self.version = version or DEFAULT
        self.seed = seed
        self.random = random.Random(seed)
        self.inputs = list(inputs or [])
        self.files = files if files is not None else {}
        self.gil = gil
        self.env: dict[str, Any] = {}
        self.globals = self.env  # the module whose code is running now
        self.frames: list[Frame] = []
        self.watch = watch  # the debugger: each step carries the variables' values
        self._seen_globals: dict[str, str] = {}
        self._seen_locals: dict[str, str] = {}
        self._seen_frame: tuple[int, ...] = ()
        self.top_current: str | None = None
        self.handling: list[LearnerError] = []  # errors being handled by `except`
        self.events: list[dict[str, Any]] = []  # the interpreter's own: call, return
        self.steps: list[Step] = []
        self.output: list[str] = []
        self._partial = ""  # printed text after the last newline
        self.count = 0
        self.iterations = 0
        self.error: LearnerError | None = None
        # running things at the same time (see scheduler.py)
        self.loop: Any = None  # the asyncio event loop while `asyncio.run()` runs
        self.threads: Any = None  # the thread scheduler, once a thread starts
        self.lane: str | None = None  # the task or thread running now
        self.lanes: list[str] = []
        self.clock = 0.0
        self.pending: tuple[str, Any] | None = None  # a thread's wait, after its statement
        self.unawaited: list[coroutine] = []
        self.stdlib: dict[str, module] = {}
        self._suspend_memo: dict[int, bool] = {}
        self._kind_memo: dict[int, str] = {}
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
            "enumerate": self._enumerate,
            "zip": self._zip,
            "reversed": self._reversed,
            "map": self._map,
            "filter": self._filter,
            "iter": self._iter,
            "next": next,
            "any": any,
            "all": all,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "callable": callable,
            "repr": repr,
            "object": object,
            "super": super,
            "property": property,
            "classmethod": classmethod,
            "staticmethod": staticmethod,
            "input": self._input,
            "open": self._open,
            **EXCEPTIONS,
        }
        from mse_codezoo import stdlib

        self.builtins.update(stdlib.newer_builtins(self.version))

    # --- running -------------------------------------------------------------

    def execute(self) -> None:
        try:
            try:
                self._body(self.program.body)
                if self.threads is not None:
                    self.threads.finish()  # Python waits for every thread before it stops
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
        for made in self.unawaited:
            if not made.started and self.error is None:
                self._emit(
                    Step(
                        made.node_id,
                        note=t(
                            "`{name}()` never ran: an `async def` runs only with `await` "
                            "or `asyncio.run({name}())`.",
                            name=made.name,
                        ),
                    )
                )
                break

    def run_steps(self) -> Iterator[Step]:
        """All steps, after running the whole program."""
        self.execute()
        yield from self.steps

    def _emit(self, step: Step) -> None:
        if self.lanes:
            step.lane = self.lane or "main"
            step.time = self.clock
        if self.watch:
            step.scope = self._watch()
        self.steps.append(step)
        if self.on_step is not None:
            self.on_step(step)

    def _watch(self) -> dict[str, Any] | None:
        """The variables for the debugger, as changes since the last step: ``g`` new or
        changed values in the program's own file scope, ``g-`` names that are gone; ``f``
        the calls running now (outermost first) whenever they change, then ``l`` holds all
        of the newest call's variables, otherwise only the changed ones (``l-`` gone)."""
        scope: dict[str, Any] = {}
        shown = _watched(self.env)
        changed = {k: v for k, v in shown.items() if self._seen_globals.get(k) != v}
        gone = [k for k in self._seen_globals if k not in shown]
        if changed:
            scope["g"] = changed
        if gone:
            scope["g-"] = gone
        self._seen_globals = shown
        calls = [f for f in self.frames if not f.comprehension and not f.is_class]
        key = tuple(id(f) for f in calls)
        local = _watched(calls[-1].locals) if calls else {}
        if key != self._seen_frame:
            scope["f"] = [f.name for f in calls]
            if local:
                scope["l"] = local
        else:
            changed = {k: v for k, v in local.items() if self._seen_locals.get(k) != v}
            gone = [k for k in self._seen_locals if k not in local]
            if changed:
                scope["l"] = changed
            if gone:
                scope["l-"] = gone
        self._seen_frame, self._seen_locals = key, local
        return scope or None

    def count_iteration(self) -> None:
        """One more item from a lazy iterator; an endless one stops at the zoo's limit."""
        self.iterations += 1
        if self.iterations > MAX_ITERATIONS:
            raise LearnerError(
                t(
                    "Your program went through more than {count} things. "
                    "Is something endless, like `itertools.count()`, missing a stop?",
                    count=MAX_ITERATIONS,
                ),
                kind="too_many_steps",
            )

    def add_lane(self, name: str) -> str:
        """A new lane under the stage for a task or thread; names stay unique."""
        if not self.lanes:
            self.lanes.append("main")
        unique, number = name, 2
        while unique in self.lanes:
            unique, number = f"{name} #{number}", number + 1
        self.lanes.append(unique)
        return unique

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
        except (
            TypeError,
            ValueError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            StopIteration,
        ) as exc:
            # a safety net: Python refused something we didn't check for ourselves
            raise self._safety_net(exc, stmt) from None

    def _safety_net(self, exc: BaseException, stmt: ir.Node) -> LearnerError:
        why = str(exc) or type(exc).__name__
        return LearnerError(
            t("Python couldn't do that: {why}", why=why),
            stmt.id,
            kind="raised" if isinstance(exc, StopIteration) else "type",
            exception=exc,
        )

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
            case ir.ClassDef():
                self._define_class(stmt)
            case ir.AnnAssign(target=target, annotation=annotation, value=value):
                frame = self._frame()
                if frame is not None and frame.is_class and isinstance(target, ir.Name):
                    from mse_codezoo.lang_python import expr_to_text

                    frame.annotations[target.name] = expr_to_text(annotation)
                if value is None:
                    self._step(stmt)
                else:
                    result = self._eval(value)
                    self._assign(target, result)
                    self._step(stmt, note=self._note(target, result))
            case ir.Return(value=value):
                result = None if value is None else self._eval(value)
                self._step(stmt, note=f"-> {_short(result)}")
                raise _Return(result)
            case ir.Global():
                if self.frames:
                    self.frames[-1].global_names.update(stmt.names)
            case ir.Nonlocal():
                if not self.frames or not self.frames[-1].closures:
                    raise LearnerError(
                        t("`nonlocal` only works in a function inside another function."),
                        kind="type",
                    )
            case ir.TypeAlias(name=name, value=value):
                from mse_codezoo.stdlib import TypeAliasValue

                self._scope_for(name)[name] = TypeAliasValue(name, value)
                self._step(stmt)
            case ir.Try():
                self._drive(self._rtry(stmt, False))
            case ir.With():
                self._drive(self._rwith(stmt, False))
            case ir.Match():
                self._drive(self._rmatch(stmt, False))
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
                self._step(stmt, note=t("lazy: unpacked when first used") if stmt.lazy else None)
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
        if isinstance(value, str | bytes):
            return isinstance(value, str)
        if callable(value) and not Runner.is_open(value):
            return False
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
        if name == "__name__":
            scope = frame.globals if frame else self.globals
            return scope.get("__name__", "__main__")
        if frame is not None:
            if name in frame.locals:
                return frame.locals[name]
            if (
                name in frame.local_names
                and name not in frame.global_names
                and not frame.is_class  # a class body falls back to the names outside
            ):
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
        from mse_codezoo.versions import NEWER_BUILTINS, version_text

        if name in NEWER_BUILTINS:
            raise LearnerError(
                t(
                    "`{name}` arrived in Python {since}; this program is set to Python {now}.",
                    name=name,
                    since=version_text(NEWER_BUILTINS[name]),
                    now=version_text(self.version),
                ),
                kind="unknown_name",
                exception=NameError(f"name '{name}' is not defined"),
            )
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
        if name in frame.nonlocal_names:
            for scope in frame.closures:
                if name in scope:
                    return scope
        return frame.locals

    def _assign(self, target: ir.Expr, value: Any) -> None:
        match target:
            case ir.Name(name=name):
                self._scope_for(name)[name] = value
            case ir.Subscript(value=container, index=index):
                self._set_item(self._eval(container), index, value)
            case ir.Attribute(value=obj, attr=attr):
                self._set_attribute(self._eval(obj), attr, value)
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
            case ir.Attribute(value=obj, attr=attr):
                owner = self._eval(obj)
                self._attribute(owner, attr)  # same errors as reading it
                self._set_attribute(owner, attr, None, delete=True)
            case _:
                raise LearnerError(t("You can't delete that."), kind="type")

    def _aug_assign(self, stmt: ir.AugAssign, target: ir.Expr, op: str, value: ir.Expr) -> None:
        if isinstance(target, ir.Attribute):
            owner = self._eval(target.value)
            old = self._attribute(owner, target.attr)
            result = self._in_place(op, old, self._eval(value))
            self._set_attribute(owner, target.attr, result)
            self._step(stmt, note=self._note(target, result))
            return
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

    def _make_function(self, node: ir.FunctionDef) -> function:
        defaults = [
            _NO_DEFAULT if p.default is None else self._eval(p.default) for p in node.params
        ]
        frame = self._frame()
        if frame is None:
            closures: list[dict[str, Any]] = []
        elif frame.is_class:
            closures = list(frame.closures)  # a method doesn't see its class body's names
        else:
            closures = [frame.locals, *frame.closures]
        globals_ = frame.globals if frame else self.globals
        return function(self, node, defaults, globals_, closures)

    def _define(self, stmt: ir.FunctionDef) -> None:
        decorators = [self._eval(d) for d in stmt.decorators]  # worked out before the def
        value: Any = self._make_function(stmt)
        for decorator in reversed(decorators):
            value = self._call_value(decorator, [value], {}, getattr(decorator, "__name__", "@"))
        self._scope_for(stmt.name)[stmt.name] = value
        keyword = "async def" if stmt.is_async else "def"
        params = ", ".join(p.name for p in stmt.params)
        self._step(stmt, note=f"{keyword} {stmt.name}({params})")

    def _lambda(self, expr: ir.Lambda) -> function:
        node = ir.FunctionDef(
            id=expr.id,
            name="<lambda>",
            params=expr.params,
            body=[ir.Return(id=expr.id, value=expr.body)],
        )
        return self._make_function(node)

    def _kind(self, node: ir.FunctionDef) -> str:
        """``function``, ``generator`` (it has ``yield``) or ``coroutine`` (``async def``)."""
        kind = self._kind_memo.get(id(node))
        if kind is None:
            gen = is_generator_body(node.body)
            if node.is_async and gen:
                kind = "async generator"
            else:
                kind = "coroutine" if node.is_async else "generator" if gen else "function"
            self._kind_memo[id(node)] = kind
        return kind

    def _depth(self) -> int:
        return sum(1 for f in self.frames if not f.comprehension and not f.is_class)

    def invoke(self, fn: function, args: list[Any], kwargs: dict[str, Any]) -> Any:
        """Call a learner function: bind its inputs, run its body on a new frame.

        A generator function or an ``async def`` doesn't run yet: the call gives back a
        generator or a coroutine that runs the body when asked.
        """
        kind = self._kind(fn.node)
        frame = self._bind(fn, args, kwargs)
        if kind == "function":
            return self._run_function(fn, frame)
        if kind == "async generator":
            raise LearnerError(
                t("An `async def` with `yield` inside isn't part of CodeZoo yet."), kind="type"
            )
        label = f"{fn.name}({', '.join(_short(frame.locals[p.name]) for p in fn.node.params)})"
        if kind == "generator":
            body = self._framed(frame, self._function_body(fn, frame, False), events=True)
            return generator(fn.name, body)
        body = self._framed(frame, self._function_body(fn, frame, False))
        made = coroutine(fn.name, label, body, self._current_statement())
        self.unawaited.append(made)
        return made

    def _current_statement(self) -> str:
        for frame in reversed(self.frames):
            if not frame.comprehension and frame.current:
                return frame.current
        return self.top_current or self.program.id

    def _bind(self, fn: function, args: list[Any], kwargs: dict[str, Any]) -> Frame:
        node = fn.node
        params = node.params
        plain = [p for p in params if p.kind == "plain"]
        rest = next((p for p in params if p.kind == "args"), None)
        options = next((p for p in params if p.kind == "kwargs"), None)
        named_ok = {p.name for p in params if p.kind in ("plain", "kwonly")}
        if len(args) > len(plain) and rest is None:
            raise self._input_error(
                fn,
                t(
                    "`{name}` takes {count} input(s), but got {got}.",
                    name=fn.name,
                    count=len(plain),
                    got=len(args),
                ),
            )
        bound: dict[str, Any] = dict(zip((p.name for p in plain), args, strict=False))
        if rest is not None:
            bound[rest.name] = tuple(args[len(plain) :])
        extra: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key in named_ok:
                if key in bound:
                    raise self._input_error(
                        fn, t("`{name}` got `{key}` twice.", name=fn.name, key=key)
                    )
                bound[key] = value
            elif options is not None:
                extra[key] = value
            else:
                raise self._input_error(
                    fn, t("`{name}` has no input called `{key}`.", name=fn.name, key=key)
                )
        if options is not None:
            bound[options.name] = extra
        for param, default in zip(params, fn.defaults, strict=True):
            if param.kind in ("plain", "kwonly") and param.name not in bound:
                if default is _NO_DEFAULT:
                    raise self._input_error(
                        fn, t("`{name}` needs the input `{key}`.", name=fn.name, key=param.name)
                    )
                bound[param.name] = default
        local_names = {p.name for p in params} | assigned_names(node.body)
        globals_declared = global_names(node.body)
        nonlocals = global_names(node.body, ir.Nonlocal)
        return Frame(
            fn.name,
            bound,
            local_names - globals_declared - nonlocals,
            globals_declared,
            fn.globals,
            fn.closures,
            function=fn,
            nonlocal_names=nonlocals,
        )

    def _too_deep(self, fn: function) -> LearnerError:
        return LearnerError(
            t(
                "`{name}` called itself too many times ({count} deep). "
                "Does it have a base case that stops it?",
                name=fn.name,
                count=MAX_DEPTH,
            ),
            kind="too_deep",
        )

    def _run_function(self, fn: function, frame: Frame) -> Any:
        depth = self._depth()
        if depth >= MAX_DEPTH:
            raise self._too_deep(fn)
        node = fn.node
        shown = [_short(frame.locals[p.name]) for p in node.params]
        self.frames.append(frame)
        self.events.append({"type": "call", "name": fn.name, "args": shown, "depth": depth + 1})
        result: Any = None
        try:
            self._step(node, note=f"{fn.name}({', '.join(shown)})")
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

    def _function_body(self, fn: function, frame: Frame, preempt: bool) -> Generator[Any, Any, Any]:
        """The body of a generator, coroutine or thread, run so it can pause."""
        node = fn.node
        shown = [_short(frame.locals[p.name]) for p in node.params]
        self._step(node, note=f"{fn.name}({', '.join(shown)})")
        try:
            yield from self._rbody(node.body, preempt)
        except _Return as returned:
            return returned.value
        except (_Break, _Continue) as signal:
            word = "break" if isinstance(signal, _Break) else "continue"
            raise LearnerError(
                t("`{word}` only works inside a loop.", word=word), frame.current
            ) from None
        return None

    def _framed(
        self, frame: Frame, body: Generator[Any, Any, Any], *, events: bool = False
    ) -> Generator[Any, Any, Any]:
        """Run ``body`` with ``frame`` on top of the call stack, taking it off whenever the
        body pauses, so the stack is right wherever the body is resumed from."""
        value: Any = None
        error: BaseException | None = None
        while True:
            depth = self._depth()
            if depth >= MAX_DEPTH and frame.function is not None:
                raise self._too_deep(frame.function)
            self.frames.append(frame)
            if events:
                self.events.append(
                    {"type": "call", "name": frame.name, "args": [], "depth": depth + 1}
                )
            try:
                request = body.send(value) if error is None else body.throw(error)
            except StopIteration as stop:
                if events:
                    self.events.append(
                        {
                            "type": "return",
                            "name": frame.name,
                            "value": _short(stop.value),
                            "depth": depth + 1,
                        }
                    )
                return stop.value
            finally:
                self._pop(frame)
            if events:  # a generator handing out a value pauses
                self.events.append(
                    {
                        "type": "return",
                        "name": frame.name,
                        "value": _short(request),
                        "depth": depth + 1,
                        "paused": True,
                    }
                )
            try:
                value, error = (yield request), None
            except GeneratorExit:
                body.close()
                raise
            except BaseException as exc:  # noqa: BLE001 - passed on into the body
                value, error = None, exc

    def _pop(self, frame: Frame) -> None:
        for index in range(len(self.frames) - 1, -1, -1):
            if self.frames[index] is frame:
                del self.frames[index]
                return

    def _input_error(self, fn: function, message: str) -> LearnerError:
        return LearnerError(message, kind="type", exception=TypeError(message))

    # --- classes ----------------------------------------------------------------------

    def _define_class(self, stmt: ir.ClassDef) -> None:
        decorators = [self._eval(d) for d in stmt.decorators]
        bases = tuple(self._eval(b) for b in stmt.bases)
        for base in bases:
            if not self._allowed_base(base):
                raise LearnerError(
                    t(
                        "A class can build on your own classes, `object`, an error like "
                        "`Exception` or `NamedTuple`, not {what}.",
                        what=describe(base),
                    ),
                    kind="type",
                    exception=TypeError("bad base class"),
                )
        if stmt.keywords:
            raise LearnerError(t("CodeZoo classes don't take options like `metaclass=`."))
        outer = self._frame()
        namespace: dict[str, Any] = {}
        closures = (
            []
            if outer is None
            else (list(outer.closures) if outer.is_class else [outer.locals, *outer.closures])
        )
        frame = Frame(
            stmt.name,
            namespace,
            assigned_names(stmt.body),
            global_names(stmt.body),
            outer.globals if outer else self.globals,
            closures,
            is_class=True,
        )
        self._step(stmt, note=f"class {stmt.name}")
        self.frames.append(frame)
        try:
            self._body(stmt.body)
        finally:
            self.frames.pop()
        for name in namespace:
            if name.startswith("__") and name.endswith("__") and name not in CLASS_DUNDERS:
                raise LearnerError(
                    t("CodeZoo classes can't define `{name}`.", name=name), kind="type"
                )
        module_name = (outer.globals if outer else self.globals).get("__name__", "__main__")
        namespace.update(__module__=module_name, __qualname__=stmt.name, __codezoo__=True)
        if frame.annotations:
            namespace["__annotations__"] = dict(frame.annotations)
        try:
            cls: Any = types.new_class(stmt.name, bases, exec_body=lambda ns: ns.update(namespace))
        except TypeError as exc:
            raise LearnerError(
                t("Python can't make the class `{name}`: {why}", name=stmt.name, why=exc),
                kind="type",
                exception=exc,
            ) from None
        for value in namespace.values():
            for fn in _functions_inside(value):
                fn.owner = cls
        for decorator in reversed(decorators):
            cls = self._call_value(decorator, [cls], {}, getattr(decorator, "__name__", "@"))
        self._scope_for(stmt.name)[stmt.name] = cls

    @staticmethod
    def _allowed_base(base: Any) -> bool:
        import typing

        if base is typing.NamedTuple or base is object:
            return True
        if not isinstance(base, type):
            return False
        if getattr(base, "__codezoo__", False):
            return True
        return issubclass(base, BaseException) and base in EXCEPTIONS.values()

    @staticmethod
    def is_open(obj: Any) -> bool:
        """Objects whose attributes programs may read: their own classes and instances,
        ``super()``, and the zoo's objects."""
        if isinstance(obj, super | ZooObject):
            return True
        if isinstance(obj, type):
            return bool(getattr(obj, "__codezoo__", False))
        return bool(getattr(type(obj), "__codezoo__", False))

    def _set_attribute(self, obj: Any, attr: str, value: Any, *, delete: bool = False) -> None:
        if isinstance(obj, module) and not delete:
            obj.names[attr] = value
            return
        own = isinstance(obj, type) or not isinstance(obj, ZooObject | super)
        if not (self.is_open(obj) and own):
            raise LearnerError(
                t("You can't give {what} a new `.{name}`.", what=describe(obj), name=attr),
                kind="type",
                exception=AttributeError(
                    f"'{type(obj).__name__}' object has no attribute '{attr}'"
                ),
            )
        self._check_dunder(attr)
        try:
            if delete:
                delattr(obj, attr)
            else:
                setattr(obj, attr, value)
        except LearnerError:
            raise
        except AttributeError as exc:  # a frozen dataclass, or a property without a setter
            raise LearnerError(
                t("`.{name}` can't be changed: {why}", name=attr, why=exc),
                kind="type",
                exception=exc,
            ) from None

    @staticmethod
    def _check_dunder(attr: str) -> None:
        if attr.startswith("__") and attr.endswith("__") and attr not in OPEN_DUNDERS:
            raise LearnerError(
                t("CodeZoo keeps `{name}` to itself.", name=attr),
                kind="unknown_name",
                exception=AttributeError(attr),
            )

    def _super(self) -> Any:
        """``super()`` inside a method: the class it was taught in, and ``self``."""
        frame = next((f for f in reversed(self.frames) if f.function is not None), None)
        fn = frame.function if frame else None
        if frame is None or fn is None or fn.owner is None or not fn.node.params:
            raise LearnerError(
                t("`super()` only works inside a method of a class."),
                kind="type",
                exception=RuntimeError("super(): no arguments"),
            )
        first = frame.locals.get(fn.node.params[0].name)
        return super(fn.owner, first)

    def _call_value(
        self, command: Any, values: list[Any], named: dict[str, Any], name: str = "it"
    ) -> Any:
        """Call anything that isn't one of the listed builtins: a class, a method, a zoo
        command or a decorator."""
        if isinstance(command, function):
            return self.invoke(command, values, named)
        if isinstance(command, types.MethodType) and isinstance(command.__func__, function):
            return self.invoke(command.__func__, [command.__self__, *values], named)
        if command is super:
            return self._super() if not values else super(*values)
        if isinstance(command, type) and (
            issubclass(command, type | ZooObject | function | module)
            and not getattr(command, "ZOO_MAKE", False)
        ):
            message = t("CodeZoo can't make new {what} like that.", what=describe(command))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        if not callable(command):
            message = t("`{name}` is {what}, not a command.", name=name, what=describe(command))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        try:
            result = command(*values, **named)
        except LearnerError:
            raise
        except StopIteration as exc:
            raise LearnerError(
                t("There is nothing left in it (`StopIteration`)."), kind="raised", exception=exc
            ) from None
        except (TypeError, ValueError, OverflowError, KeyError, IndexError, AttributeError) as exc:
            raise LearnerError(
                t("`{name}` can't use these inputs: {why}.", name=name, why=exc),
                kind="type",
                exception=exc,
            ) from None
        except RecursionError:
            raise LearnerError(
                t("Your program went too deep for the zoo to follow."), kind="too_deep"
            ) from None
        return self._checked(result)

    # --- running so a body can pause: generators, coroutines, threads -------------------

    def _drive(self, body: Generator[Any, Any, Any]) -> Any:
        """Run a pausable body that can't actually pause here (no ``await`` or ``yield``)."""
        try:
            body.send(None)
        except StopIteration as stop:
            return stop.value
        raise LearnerError(t("CodeZoo can't pause here."))  # pragma: no cover

    def _suspends(self, stmt: ir.Stmt) -> bool:
        """Whether a statement has a ``yield`` or ``await`` of its own (not in a def inside)."""
        found = self._suspend_memo.get(id(stmt))
        if found is None:
            found = any(
                isinstance(n, SUSPENDS) or (isinstance(n, ir.With) and n.is_async)
                for n in local_walk(stmt)
            )
            self._suspend_memo[id(stmt)] = found
        return found

    def _rbody(self, stmts: list[ir.Stmt], preempt: bool) -> Generator[Any, Any, None]:
        for stmt in stmts:
            if preempt or self._suspends(stmt):
                yield from self._rstmt(stmt, preempt)
            else:
                self._stmt(stmt)

    def _rstmt(self, stmt: ir.Stmt, preempt: bool) -> Generator[Any, Any, None]:
        if isinstance(stmt, ir.Comment | ir.Pass):
            return
        self._set_current(stmt.id)
        try:
            self._tick(stmt)
            yield from self._rexec(stmt, preempt)
        except LearnerError as exc:
            if exc.node_id is None:
                exc.node_id = stmt.id
                exc.traceback = self._traceback()
            raise
        except (
            TypeError,
            ValueError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            StopIteration,
        ) as exc:
            raise self._safety_net(exc, stmt) from None

    def _pause(self, preempt: bool) -> Generator[Any, Any, None]:
        """In a thread, other threads may run between any two statements."""
        if preempt:
            request, self.pending = self.pending or ("preempt", None), None
            yield request

    def _rexec(self, stmt: ir.Stmt, preempt: bool) -> Generator[Any, Any, None]:
        match stmt:
            case ir.If(test=test, body=body, orelse=orelse):
                yield from self._resolve(test)
                passed = self._test(test)
                self._step(stmt, note=f"-> {passed}")
                yield from self._pause(preempt)
                yield from self._rbody(body if passed else orelse, preempt)
            case ir.While(test=test, body=body):
                while True:
                    yield from self._resolve(test)
                    passed = self._test(test)
                    self._step(stmt, note=f"-> {passed}")
                    yield from self._pause(preempt)
                    if not passed:
                        break
                    try:
                        yield from self._rbody(body, preempt)
                    except _Break:
                        break
                    except _Continue:
                        pass
                    self._tick(stmt)
            case ir.For(target=target, iter=iterable, body=body):
                yield from self._resolve(iterable)
                values = self._loop_values(self._eval(iterable))
                first = True
                while True:
                    try:
                        item = next(values)
                    except StopIteration:
                        break
                    if not first:
                        self._tick(stmt)
                    first = False
                    self._assign(target, item)
                    self._step(stmt, note=self._note(target, item))
                    yield from self._pause(preempt)
                    try:
                        yield from self._rbody(body, preempt)
                    except _Break:
                        break
                    except _Continue:
                        continue
            case ir.Try():
                yield from self._rtry(stmt, preempt)
            case ir.With():
                yield from self._rwith(stmt, preempt)
            case ir.Match():
                yield from self._rmatch(stmt, preempt)
            case _:
                yield from self._resolve(stmt)
                self._exec(stmt)
                yield from self._pause(preempt)

    def _loop_values(self, values: Any) -> Iterator[Any]:
        if not self._iterable(values):
            raise LearnerError(
                t(
                    "A `for` loop needs something to go through, like `range(5)`, not {what}.",
                    what=describe(values),
                ),
                kind="type",
                exception=TypeError(f"'{type(values).__name__}' object is not iterable"),
            )
        return iter(values)

    def _resolve(self, node: ir.Node) -> Generator[Any, Any, None]:
        """Do the ``await`` and ``yield`` parts of a statement first (innermost first), so the
        rest of it can then be worked out the usual way."""
        found = _suspend_order(node)
        if not found:
            return
        frame = self._frame()
        fn = frame.function if frame is not None else None
        for part in found:
            if isinstance(part, ir.Await) and (fn is None or not fn.node.is_async):
                raise LearnerError(
                    t("`await` only works inside an `async def`."),
                    kind="type",
                    exception=SyntaxError("'await' outside async function"),
                )
            assert frame is not None
            match part:
                case ir.Yield(value=value):
                    handed = None if value is None else self._eval(value)
                    result = yield handed
                case ir.YieldFrom(value=value):
                    result = yield from self._yield_from(self._eval(value))
                case ir.Await(value=value):
                    result = yield from self._await(self._eval(value), part)
            frame.resolved[part.id] = result

    def _yield_from(self, source: Any) -> Generator[Any, Any, Any]:
        if not self._iterable(source):
            message = t(
                "`yield from` needs something with items in it, not {what}.",
                what=describe(source),
            )
            raise LearnerError(message, kind="type", exception=TypeError(message))
        items = iter(source)
        sent = None
        while True:
            try:
                if isinstance(items, generator):
                    item = items.send(sent)
                else:
                    item = next(items)
            except StopIteration as stop:
                return stop.value
            sent = yield item

    def _await(self, value: Any, node: ir.Node) -> Generator[Any, Any, Any]:
        if not isinstance(value, Awaitable):
            message = t(
                "`await` needs something to wait for, like `asyncio.sleep(1)` or a task, "
                "not {what}.",
                what=describe(value),
            )
            raise LearnerError(message, kind="type", exception=TypeError(message))
        self._step(node, note=t("waiting"))
        return (yield from value.wait(self))

    def _resolved(self, expr: ir.Expr) -> Any:
        frame = self._frame()
        if frame is not None and expr.id in frame.resolved:
            return frame.resolved.pop(expr.id)
        if isinstance(expr, ir.Await):
            raise LearnerError(
                t(
                    "`await` only works inside an `async def`; start the program with "
                    "`asyncio.run(main())`."
                ),
                kind="type",
                exception=SyntaxError("'await' outside async function"),
            )
        raise LearnerError(
            t("`yield` only works inside a function, on a line of its own or after `=`."),
            kind="type",
            exception=SyntaxError("'yield' outside function"),
        )

    # --- errors --------------------------------------------------------------------

    def _rtry(self, stmt: ir.Try, preempt: bool) -> Generator[Any, Any, None]:
        self._step(stmt)
        try:
            try:
                yield from self._rbody(stmt.body, preempt)
            except LearnerError as error:
                if error.exception is None:
                    raise
                if stmt.star:
                    yield from self._rstar(stmt, error, preempt)
                    return
                handler = self._handler_for(stmt, error.exception)
                if handler is None:
                    raise
                yield from self._rhandle(handler, error, error.exception, preempt)
            else:
                yield from self._rbody(stmt.orelse, preempt)
        finally:
            if stmt.finalbody:
                yield from self._rbody(stmt.finalbody, preempt)

    def _rhandle(
        self, handler: ir.ExceptHandler, error: LearnerError, value: BaseException, preempt: bool
    ) -> Generator[Any, Any, None]:
        self._step(handler, note=type(value).__name__)
        scope = self._scope_for(handler.name) if handler.name else None
        if handler.name and scope is not None:
            scope[handler.name] = value
        self.handling.append(error)
        try:
            yield from self._rbody(handler.body, preempt)
        finally:
            self.handling.pop()
            if handler.name and scope is not None:
                scope.pop(handler.name, None)

    def _rstar(self, stmt: ir.Try, error: LearnerError, preempt: bool) -> Generator[Any, Any, None]:
        """``except*``: each handler takes the errors of its kind out of the group."""
        assert error.exception is not None
        rest: BaseException | None = error.exception
        if not isinstance(rest, BaseExceptionGroup):
            rest = ExceptionGroup("", [rest])  # type: ignore[list-item]
        for handler in stmt.handlers:
            if rest is None:
                break
            kinds = self._eval(handler.kind) if handler.kind is not None else BaseException
            options = kinds if isinstance(kinds, tuple) else (kinds,)
            matched, rest = rest.split(options)
            if matched is not None:
                yield from self._rhandle(handler, error, matched, preempt)
        if rest is not None:
            raise LearnerError(
                self._uncaught_message(LearnerError("", exception=rest)),
                kind="raised",
                exception=rest,
            )

    # --- with --------------------------------------------------------------------------

    def _rwith(self, stmt: ir.With, preempt: bool) -> Generator[Any, Any, None]:
        self._step(stmt)
        entered: list[Any] = []
        try:
            for item in stmt.items:
                yield from self._resolve(item.context)
                context = self._eval(item.context)
                value = yield from self._enter(context, stmt.is_async)
                entered.append(context)
                if item.target is not None:
                    self._assign(item.target, value)
            yield from self._rbody(stmt.body, preempt)
        except LearnerError as error:
            pending: LearnerError | None = error
            while entered:
                context = entered.pop()
                if (yield from self._exit(context, pending, stmt.is_async)):
                    pending = None  # __exit__ said it handled the error
            if pending is not None:
                raise
            return
        except _Signal:
            while entered:
                yield from self._exit(entered.pop(), None, stmt.is_async)
            raise
        while entered:
            yield from self._exit(entered.pop(), None, stmt.is_async)

    def _enter(self, context: Any, is_async: bool) -> Generator[Any, Any, Any]:
        if isinstance(context, ZooObject) and hasattr(context, "zoo_enter"):
            if is_async != bool(getattr(context, "ASYNC", False)):
                raise self._with_error(context, is_async)
            return (yield from context.zoo_enter(self))
        name = "__aenter__" if is_async else "__enter__"
        if self.is_open(context) and hasattr(type(context), name):
            result = self._call_value(self._attribute(context, name), [], {}, name)
            if is_async:
                return (yield from self._await(result, ir.Pass(id=self._current_statement())))
            return result
        raise self._with_error(context, is_async)

    def _with_error(self, context: Any, is_async: bool) -> LearnerError:
        if is_async:
            message = t("`async with` needs something like an `asyncio.Lock()`, not {what}.")
        else:
            message = t(
                "`with` needs something that can be put back, like `open(...)` or a lock, not {what}."  # noqa: E501
            )
        text = message.replace("{what}", describe(context))
        return LearnerError(text, kind="type", exception=TypeError(text))

    def _exit(
        self, context: Any, error: LearnerError | None, is_async: bool
    ) -> Generator[Any, Any, bool]:
        if isinstance(context, ZooObject) and hasattr(context, "zoo_exit"):
            return bool((yield from context.zoo_exit(self, error)))
        name = "__aexit__" if is_async else "__exit__"
        value = error.exception if error is not None else None
        args = [None, None, None] if value is None else [type(value), value, None]
        result = self._call_value(self._attribute(context, name), args, {}, name)
        if is_async:
            result = yield from self._await(result, ir.Pass(id=self._current_statement()))
        # an error the zoo itself raised (a bump, a limit) can't be swallowed
        return bool(result) and value is not None

    # --- match ---------------------------------------------------------------------------

    def _rmatch(self, stmt: ir.Match, preempt: bool) -> Generator[Any, Any, None]:
        yield from self._resolve(stmt.subject)
        subject = self._eval(stmt.subject)
        self._step(stmt, note=f"-> {_short(subject)}")
        for case in stmt.cases:
            caught: dict[str, Any] = {}
            if not self._match(case.pattern, subject, caught):
                continue
            for name, value in caught.items():
                self._scope_for(name)[name] = value
            if case.guard is not None:
                yield from self._resolve(case.guard)
                if not self._test(case.guard):
                    continue
            self._step(case, note="case")
            yield from self._rbody(case.body, preempt)
            return

    def _match(self, pattern: ir.Pattern, value: Any, caught: dict[str, Any]) -> bool:
        match pattern:
            case ir.PatternCapture(name=name):
                if name is not None:
                    caught[name] = value
                return True
            case ir.PatternValue(value=ir.Const(value=None | True | False as constant)):
                return value is constant
            case ir.PatternValue(value=expected):
                return bool(value == self._eval(expected))
            case ir.PatternAs(pattern=inner, name=name):
                if not self._match(inner, value, caught):
                    return False
                caught[name] = value
                return True
            case ir.PatternOr(patterns=options):
                for option in options:
                    tried: dict[str, Any] = {}
                    if self._match(option, value, tried):
                        caught.update(tried)
                        return True
                return False
            case ir.PatternSequence(patterns=parts):
                return self._match_sequence(parts, value, caught)
            case ir.PatternMapping(keys=keys, patterns=parts, rest=rest):
                if not isinstance(value, Mapping):
                    return False
                wanted = [self._eval(k) for k in keys]
                for key, part in zip(wanted, parts, strict=True):
                    if key not in value or not self._match(part, value[key], caught):
                        return False
                if rest is not None:
                    caught[rest] = {k: v for k, v in value.items() if k not in wanted}
                return True
            case ir.PatternClass(cls=cls_expr, patterns=parts, kwd_names=names, kwd_patterns=kwds):
                cls = self._eval(cls_expr)
                if not isinstance(cls, type):
                    message = t("`case` needs a class before the brackets, not {what}.")
                    raise LearnerError(message.replace("{what}", describe(cls)), kind="type")
                if not isinstance(value, cls):
                    return False
                if parts:
                    if cls in (bool, bytes, dict, float, frozenset, int, list, set, str, tuple):
                        if len(parts) > 1 or not self._match(parts[0], value, caught):
                            return False
                    else:
                        fields_ = getattr(cls, "__match_args__", ())
                        if len(parts) > len(fields_):
                            raise LearnerError(
                                t(
                                    "`{name}` can't be matched with {count} values in brackets.",
                                    name=cls.__name__,
                                    count=len(parts),
                                ),
                                kind="type",
                                exception=TypeError("too many positional sub-patterns"),
                            )
                        for name, part in zip(fields_, parts, strict=False):
                            if not hasattr(value, name) or not self._match(
                                part, getattr(value, name), caught
                            ):
                                return False
                for name, part in zip(names, kwds, strict=True):
                    self._check_dunder(name)
                    if not hasattr(value, name) or not self._match(
                        part, getattr(value, name), caught
                    ):
                        return False
                return True
        raise LearnerError(t("CodeZoo can't match `{what}` yet.", what=type(pattern).__name__))

    def _match_sequence(self, parts: list[ir.Pattern], value: Any, caught: dict[str, Any]) -> bool:
        if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
            return False
        items = list(value)
        star = next((i for i, p in enumerate(parts) if isinstance(p, ir.PatternStar)), None)
        if star is None:
            if len(items) != len(parts):
                return False
            return all(self._match(p, v, caught) for p, v in zip(parts, items, strict=True))
        before, after = parts[:star], parts[star + 1 :]
        if len(items) < len(before) + len(after):
            return False
        for part, item in zip(before, items, strict=False):
            if not self._match(part, item, caught):
                return False
        tail = items[len(items) - len(after) :] if after else []
        for part, item in zip(after, tail, strict=True):
            if not self._match(part, item, caught):
                return False
        starred = parts[star]
        assert isinstance(starred, ir.PatternStar)
        if starred.name is not None:
            caught[starred.name] = items[len(before) : len(items) - len(after)]
        return True

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
        if stmt.lazy and not stmt.names and stmt.module not in self.loaded:
            from mse_codezoo.stdlib import LazyModule

            self._scope_for(stmt.module)[stmt.module] = LazyModule(stmt.module)
            return
        loaded = self._load_module(stmt.module)
        if not stmt.names:
            self._scope_for(stmt.module)[stmt.module] = loaded
            return
        for name in stmt.names:
            if name not in loaded.names and name in loaded.newer:
                raise self._newer_name(loaded, name)
            if name not in loaded.names:
                raise LearnerError(
                    t("`{module}` has no `{name}` in it.", module=stmt.module, name=name),
                    kind="unknown_name",
                    exception=ImportError(f"cannot import name '{name}' from '{stmt.module}'"),
                )
            self._scope_for(name)[name] = loaded.names[name]

    def _newer_name(self, source: module, name: str) -> LearnerError:
        from mse_codezoo.versions import version_text

        return LearnerError(
            t(
                "`{module}.{name}` arrived in Python {since}; this program is set to Python {now}.",
                module=source.name,
                name=name,
                since=version_text(source.newer[name]),
                now=version_text(self.version),
            ),
            kind="unknown_name",
            exception=AttributeError(name),
        )

    def _load_module(self, name: str) -> module:
        if name in self.loaded:
            return self.loaded[name]
        source = self.modules_source.get(name)
        if source is None:
            from mse_codezoo import stdlib

            made = stdlib.load(self, name)
            if made is not None:
                self.loaded[name] = made
                return made
            raise LearnerError(
                t(
                    "There is no helper file called `{name}.py` here.",
                    name=name,
                ),
                kind="unknown_name",
                exception=ModuleNotFoundError(f"No module named '{name}'"),
            )
        program = source if isinstance(source, ir.Program) else self._parse_module(name, source)
        namespace: dict[str, Any] = {"__name__": name}
        result = module(name, namespace)
        self.loaded[name] = result  # before running it, so a loop of imports stops
        self.events.append({"type": "import", "module": name})
        outer, saved_frames = self.globals, self.frames
        self.globals, self.frames = namespace, []
        try:
            self._body(program.body)
        finally:
            self.globals, self.frames = outer, saved_frames
        return result

    def _parse_module(self, name: str, source: str) -> ir.Program:
        from mse_codezoo.lang_python import parse

        parsed = parse(source, self.version, id_prefix=f"{name}:")
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
            case ir.Lambda():
                return self._lambda(expr)
            case ir.Yield() | ir.YieldFrom() | ir.Await():
                return self._resolved(expr)
            case ir.TString(parts=parts):
                return self._template(parts)
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
                if not isinstance(other, Mapping):
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
        if outer is None:
            closures: list[dict[str, Any]] = []
        elif outer.is_class:
            closures = list(outer.closures)
        else:
            closures = [outer.locals, *outer.closures]
        frame = Frame(
            "<comprehension>",
            {},
            set(),
            set(outer.global_names) if outer else set(),
            outer.globals if outer else self.globals,
            closures,
            comprehension=True,
        )
        for gen in expr.generators:
            frame.local_names |= assigned_names(
                [ir.Assign(target=gen.target, value=ir.Const(value=None))]
            )
        if expr.kind == "generator":
            first = self._eval(expr.generators[0].iter)  # worked out now, like Python
            if not self._iterable(first):
                message = t(
                    "A `for` loop needs something to go through, like `range(5)`, not {what}.",
                    what=describe(first),
                )
                raise LearnerError(message, kind="type", exception=TypeError(message))
            return generator("<genexpr>", self._framed(frame, self._lazy_items(expr, first)))
        items: list[Any] = []
        pairs: list[tuple[Any, Any]] = []

        def loop(level: int) -> None:
            if level == len(expr.generators):
                if expr.kind == "dict":
                    assert expr.value is not None
                    pairs.append((self._eval(expr.elt), self._eval(expr.value)))
                elif isinstance(expr.elt, ir.Starred):  # [*cell for cell in combs] (3.15)
                    items.extend(self._elements([expr.elt]))
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

    def _lazy_items(self, expr: ir.Comprehension, first: Any) -> Generator[Any, Any, None]:
        """A generator expression's items, worked out one at a time when asked."""

        def loop(level: int, values: Any) -> Generator[Any, Any, None]:
            gen = expr.generators[level]
            for value in values:
                self._tick(expr)
                self._assign(gen.target, value)
                if not all(self._test(condition) for condition in gen.ifs):
                    continue
                if level + 1 < len(expr.generators):
                    inner = self._eval(expr.generators[level + 1].iter)
                    yield from loop(level + 1, self._loop_values(inner))
                elif isinstance(expr.elt, ir.Starred):
                    yield from self._elements([expr.elt])
                else:
                    yield self._eval(expr.elt)

        yield from loop(0, first)

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
            value = self._eval(keyword.value)
            if keyword.name is not None:
                named[keyword.name] = value
                continue
            if not isinstance(value, Mapping):
                message = t("`**` needs a dictionary, not {what}.", what=describe(value))
                raise LearnerError(message, kind="type", exception=TypeError(message))
            for key, item in value.items():
                if not isinstance(key, str):
                    message = t("The names of named inputs must be text.")
                    raise LearnerError(message, kind="type", exception=TypeError(message))
                if key in named:
                    message = t("The input `{key}` is given twice.", key=key)
                    raise LearnerError(message, kind="type", exception=TypeError(message))
                named[key] = item
        return named

    def _is_builtin(self, command: Any) -> bool:
        return any(command is b for b in self.builtins.values()) or any(
            command is a for a in self.actions.values()
        )

    def _call(self, func: str, args: list[ir.Expr], keywords: list[ir.Keyword]) -> Any:
        command = self._lookup(func)
        if command is super and not args and not keywords:
            return self._super()
        if not callable(command) or isinstance(command, range):
            message = t("`{name}` is {what}, not a command.", name=func, what=describe(command))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        values = self._elements(args)
        named = self._keywords(keywords)
        if isinstance(command, function):
            return self.invoke(command, values, named)
        if self._is_builtin(command) and command is not super:
            return self._call_builtin(func, command, values, named)
        return self._call_value(command, values, named, func)

    def _call_builtin(
        self, func: str, command: Callable[..., Any], values: list[Any], named: dict[str, Any]
    ) -> Any:
        builtin_name = next((n for n, b in self.builtins.items() if b is command), None)
        allowed = BUILTIN_KEYWORDS.get(builtin_name or "", ())
        if builtin_name in ("dict", "frozendict"):
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
        except StopIteration as exc:
            raise LearnerError(
                t("There is nothing left in it (`StopIteration`)."), kind="raised", exception=exc
            ) from None
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
        from mse_codezoo.stdlib import LazyModule

        if isinstance(obj, LazyModule):
            obj = self._load_module(obj.name)
        if isinstance(obj, ZooObject):
            if attr in type(obj).ZOO_ATTRS:
                return getattr(obj, attr)
            raise LearnerError(
                t("{what} has no `.{name}`.", what=describe(obj).capitalize(), name=attr),
                kind="unknown_name",
                exception=AttributeError(
                    f"'{type(obj).__name__}' object has no attribute '{attr}'"
                ),
            )
        if self.is_open(obj):
            self._check_dunder(attr)
            try:
                return getattr(obj, attr)
            except LearnerError:
                raise
            except AttributeError as exc:
                known = [n for n in dir(obj) if not n.startswith("__")]
                close = difflib.get_close_matches(attr, known, n=1)
                hint = t(" Did you mean `{name}`?", name=f".{close[0]}") if close else ""
                raise LearnerError(
                    t(
                        "{what} has no `.{name}`.{hint}",
                        what=describe(obj).capitalize(),
                        name=attr,
                        hint=hint,
                    ),
                    kind="unknown_name",
                    exception=exc,
                ) from None
        if isinstance(obj, property) and attr in ("setter", "getter", "deleter"):
            return getattr(obj, attr)
        if isinstance(obj, BaseExceptionGroup) and attr in ("exceptions", "message"):
            return getattr(obj, attr)
        if isinstance(obj, function) and attr == "__wrapped__":
            return obj.__wrapped__
        if isinstance(obj, module):
            if attr not in obj.names and attr in obj.newer:
                raise self._newer_name(obj, attr)
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
        from mse_codezoo.stdlib import LazyModule

        if isinstance(obj, LazyModule):
            obj = self._load_module(obj.name)
        if isinstance(obj, module) or self.is_open(obj) or isinstance(obj, property):
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
            if self._is_builtin(command) and command is not super:
                return self._call_builtin(method, command, values, named)
            return self._call_value(command, values, named, method)
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
        if isinstance(value, Mapping):
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

    # --- builtins that need the runner ------------------------------------------------

    def _lazy(self, name: str, source: Iterator[Any]) -> iterator:
        return iterator(self, name, source)

    def _zip(self, *items: Any, strict: bool = False) -> iterator:
        return self._lazy("zip", zip(*items, strict=strict))

    def _enumerate(self, items: Any, start: int = 0) -> iterator:
        return self._lazy("enumerate", enumerate(items, start))

    def _reversed(self, items: Any) -> iterator:
        return self._lazy("reversed", reversed(items))

    def _map(self, func: Any, *items: Any) -> iterator:
        if not callable(func):
            raise TypeError(f"'{type(func).__name__}' object is not callable")
        return self._lazy("map", map(func, *items))

    def _filter(self, func: Any, items: Any) -> iterator:
        return self._lazy("filter", filter(func, items))

    def _iter(self, items: Any) -> Any:
        if isinstance(items, generator | iterator):
            return items
        return self._lazy("iterator", iter(items))

    def _template(self, parts: list[ir.Expr]) -> Any:
        from mse_codezoo.lang_python import expr_to_text
        from mse_codezoo.stdlib import Interpolation, Template

        strings: list[str] = [""]
        values: list[Interpolation] = []
        for part in parts:
            if isinstance(part, ir.Const):
                strings[-1] += str(part.value)
            else:
                assert isinstance(part, ir.FormattedValue)
                values.append(
                    Interpolation(
                        self._eval(part.value),
                        expr_to_text(part.value),
                        part.conversion,
                        part.spec or "",
                    )
                )
                strings.append("")
        return Template(tuple(strings), tuple(values))

    def _input(self, prompt: Any = "") -> str:
        text = str(prompt)
        if text:
            self._print(text, end="")
        if not self.inputs:
            raise LearnerError(
                t("The program asked for an answer, but nobody is there to type any more."),
                kind="raised",
                exception=EOFError("EOF when reading a line"),
            )
        answer = self.inputs.pop(0)
        self.events.append({"type": "input", "prompt": text, "answer": answer})
        return answer

    def _open(self, file: Any, mode: str = "r", encoding: str | None = None) -> Any:
        from mse_codezoo.stdlib import ZooFile

        return ZooFile.open(self, file, mode)

    def _print(self, *args: Any, sep: Any = " ", end: Any = "\n") -> None:
        for name, value in (("sep", sep), ("end", end)):
            if value is not None and not isinstance(value, str):
                message = t("`{key}=` needs text, not {what}.", key=name, what=describe(value))
                raise LearnerError(message, kind="type", exception=TypeError(message))
        sep = " " if sep is None else sep
        end = "\n" if end is None else end
        try:
            printed = sep.join(str(arg) for arg in args) + end
        except RecursionError:
            raise LearnerError(
                t("Your program went too deep for the zoo to follow."), kind="too_deep"
            ) from None
        text = self._partial + printed
        self._checked(text)
        # the step that printed carries the text, so a console can show it as the run plays
        self.events.append({"type": "print", "text": printed})
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
    *,
    world: Any = None,
    version: tuple[int, int] | None = None,
    seed: int = 0,
    inputs: list[str] | None = None,
    files: dict[str, str] | None = None,
    gil: bool = True,
    watch: bool = False,
) -> RunResult:
    """Run to the end and collect every step (``watch``: with the variables' values).

    ``world`` (if given) supplies the actions, the event drain, the answers for
    ``input()``, the files and the GIL setting, and is told about the runner, so tricks
    that take time can use its clock.
    """
    if world is not None:
        actions = world.actions() if actions is None else actions
        drain_events = drain_events or world.drain_events
        inputs = world.inputs if inputs is None else inputs
        files = world.files if files is None else files
        gil = world.gil
    runner = Runner(
        program,
        actions,
        drain_events,
        max_steps,
        modules=modules,
        on_step=on_step,
        version=version,
        seed=seed,
        inputs=inputs,
        files=files,
        gil=gil,
        watch=watch,
    )
    if world is not None:
        world.runner = runner
    runner.execute()
    return RunResult(
        runner.steps,
        runner.output,
        runner.error,
        time=runner.clock,
        lanes=list(runner.lanes),
        files=dict(runner.files),
    )
