"""The standard modules a program may ``import``, in versions that are safe in the zoo.

Each module is built per run, so ``random`` follows the run's seed, ``time`` reads the
simulated clock and ``asyncio`` / ``threading`` run on the zoo's own scheduler. Anything
that hands out values one by one goes through a counting iterator, so an endless one
stops at the zoo's limit. Files live in the run's little in-memory disk. Standard library
only.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import itertools
import json
import math
import string
import types
import typing
from collections.abc import Callable, Generator, Iterator, Mapping
from typing import Any

from mse_codezoo import ir
from mse_codezoo.i18n import t
from mse_codezoo.interpreter import (
    MAX_FILES,
    MAX_ITEMS,
    MAX_TEXT,
    LearnerError,
    Runner,
    ZooObject,
    describe,
    module,
)
from mse_codezoo.versions import NEWER_BUILTINS, NEWER_MODULE_NAMES

MAX_FACTORIAL = 1000
MAX_FILE_NAME = 40


# --- small zoo objects ----------------------------------------------------------------


class LazyModule(ZooObject):
    """``lazy import map`` (Python 3.15): the module is unpacked when first used."""

    KIND = "a helper that isn't unpacked yet"

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<lazy module '{self.name}'>"


class TypeAliasValue(ZooObject):
    """``type Stack = list[int]`` (Python 3.12)."""

    ZOO_ATTRS = ("__name__",)
    KIND = "a type alias"

    def __init__(self, name: str, value: ir.Expr) -> None:
        self.__name__ = name
        self.value = value

    def __repr__(self) -> str:
        return self.__name__


class Interpolation(ZooObject):
    """One ``{value}`` part of a template string."""

    ZOO_ATTRS = ("value", "expression", "conversion", "format_spec")
    KIND = "an interpolation"

    def __init__(self, value: Any, expression: str, conversion: str | None, spec: str) -> None:
        self.value = value
        self.expression = expression
        self.conversion = conversion
        self.format_spec = spec

    def __repr__(self) -> str:
        return f"Interpolation({self.value!r}, {self.expression!r})"


class Template(ZooObject):
    """What a template string ``t"..."`` makes (Python 3.14): the text parts and the
    values, kept apart, so a program can check every value before using it."""

    ZOO_ATTRS = ("strings", "interpolations", "values")
    KIND = "a template"

    def __init__(self, strings: tuple[str, ...], interpolations: tuple[Interpolation, ...]):
        self.strings = strings
        self.interpolations = interpolations

    @property
    def values(self) -> tuple[Any, ...]:
        return tuple(i.value for i in self.interpolations)

    def __iter__(self) -> Iterator[Any]:
        for number, text in enumerate(self.strings):
            if text:
                yield text
            if number < len(self.interpolations):
                yield self.interpolations[number]

    def __repr__(self) -> str:
        return f"Template(strings={self.strings!r}, interpolations={self.interpolations!r})"


class Sentinel(ZooObject):
    """``MISSING = sentinel("MISSING")`` (Python 3.15): a value that means "nothing given",
    different from ``None``."""

    KIND = "a sentinel"

    def __init__(self, name: str) -> None:
        self.name = str(name)

    def __repr__(self) -> str:
        return self.name


class frozendict(Mapping[Any, Any], ZooObject):  # noqa: N801 - Python 3.15's builtin
    """A dictionary that can't change (Python 3.15)."""

    ZOO_ATTRS = ("get", "keys", "values", "items", "copy")
    KIND = "a frozen dictionary"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._data = dict(*args, **kwargs)
        if len(self._data) > MAX_ITEMS:
            raise ValueError("too many items")

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        return hash(frozenset(self._data.items()))

    def __or__(self, other: Any) -> frozendict:
        return frozendict({**self._data, **dict(other)})

    def copy(self) -> frozendict:
        return self

    def __repr__(self) -> str:
        return f"frozendict({self._data!r})"


frozendict.__module__ = "builtins"


def sentinel(name: Any) -> Sentinel:
    return Sentinel(name)


def newer_builtins(version: tuple[int, int]) -> dict[str, Any]:
    """Builtins of releases after 3.11 that ``version`` has."""
    made = {"frozendict": frozendict, "sentinel": sentinel}
    return {name: made[name] for name, since in NEWER_BUILTINS.items() if version >= since}


# --- files -------------------------------------------------------------------------------


class ZooFile(ZooObject):
    """A file on the run's little in-memory disk."""

    ZOO_ATTRS = ("read", "readline", "readlines", "write", "close", "closed", "name", "mode")
    KIND = "a file"

    def __init__(self, runner: Runner, name: str, mode: str) -> None:
        self.runner = runner
        self.name = name
        self.mode = mode
        self.closed = False
        self.position = 0

    @classmethod
    def open(cls, runner: Runner, name: Any, mode: Any = "r") -> ZooFile:
        if (
            not isinstance(name, str)
            or not name
            or len(name) > MAX_FILE_NAME
            or any(c in name for c in "/\\:")
        ):
            message = t('A file name is short text without folders, like "scores.txt".')
            raise LearnerError(message, kind="type", exception=ValueError(message))
        kind = str(mode).replace("t", "")
        if kind not in ("r", "w", "a"):
            message = t('CodeZoo opens files with "r" (read), "w" (write) or "a" (add).')
            raise LearnerError(message, kind="type", exception=ValueError(message))
        files = runner.files
        if kind == "r" and name not in files:
            raise LearnerError(
                t("There is no file called {name}.", name=repr(name)),
                kind="raised",
                exception=FileNotFoundError(2, "No such file or directory", name),
            )
        if name not in files and len(files) >= MAX_FILES:
            raise LearnerError(t("The zoo's disk is full: too many files."), kind="type")
        if kind == "w":
            files[name] = ""
        files.setdefault(name, "")
        runner.events.append({"type": "file", "name": name, "mode": kind})
        return cls(runner, name, kind)

    def _check(self, want: str) -> None:
        if self.closed:
            message = t("The file {name} is closed already.", name=repr(self.name))
            raise LearnerError(message, kind="type", exception=ValueError(message))
        if (want == "r") != (self.mode == "r"):
            message = t("The file {name} wasn't opened for that.", name=repr(self.name))
            raise LearnerError(message, kind="type", exception=OSError(message))

    def read(self) -> str:
        self._check("r")
        text = self.runner.files[self.name][self.position :]
        self.position += len(text)
        return text

    def readline(self) -> str:
        self._check("r")
        text = self.runner.files[self.name]
        end = text.find("\n", self.position)
        end = len(text) if end < 0 else end + 1
        line = text[self.position : end]
        self.position = end
        return line

    def readlines(self) -> list[str]:
        lines = []
        while line := self.readline():
            lines.append(line)
        return lines

    def __iter__(self) -> ZooFile:
        return self

    def __next__(self) -> str:
        self.runner.count_iteration()
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    def write(self, text: Any) -> int:
        self._check("w")
        if not isinstance(text, str):
            message = t("`.write()` needs text, not {what}.", what=describe(text))
            raise LearnerError(message, kind="type", exception=TypeError(message))
        files = self.runner.files
        if len(files[self.name]) + len(text) > MAX_TEXT * 10:
            raise LearnerError(t("That file would be far too long for the zoo."), kind="type")
        files[self.name] += text
        return len(text)

    def close(self) -> None:
        self.closed = True

    def zoo_enter(self, runner: Runner) -> Generator[Any, Any, Any]:
        return self
        yield  # pragma: no cover

    def zoo_exit(self, runner: Runner, error: Any) -> Generator[Any, Any, bool]:
        self.close()
        return False
        yield  # pragma: no cover

    def __repr__(self) -> str:
        return f"<file {self.name!r} mode={self.mode!r}>"


# --- functools ---------------------------------------------------------------------------

CacheInfo = collections.namedtuple("CacheInfo", "hits misses maxsize currsize")


class Cached(ZooObject):
    """A function that remembers its answers (``@cache``, ``@lru_cache``)."""

    ZOO_ATTRS = ("cache_info", "cache_clear", "__name__", "__wrapped__")
    KIND = "a function that remembers"

    def __init__(self, runner: Runner, func: Any, maxsize: int | None) -> None:
        self.runner = runner
        self.__wrapped__ = func
        self.maxsize = maxsize
        self.store: dict[Any, Any] = {}
        self.hits = 0
        self.misses = 0

    @property
    def __name__(self) -> str:  # noqa: PLW3201
        return getattr(self.__wrapped__, "__name__", "function")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        key = (args, tuple(sorted(kwargs.items())))
        try:
            hash(key)
        except TypeError:
            message = t("A remembering function needs inputs that can be dictionary keys.")
            raise LearnerError(message, kind="type", exception=TypeError(message)) from None
        if key in self.store:
            self.hits += 1
            return self.store[key]
        self.misses += 1
        value = self.runner._call_value(self.__wrapped__, list(args), kwargs, self.__name__)
        if self.maxsize is not None and len(self.store) >= self.maxsize > 0:
            self.store.pop(next(iter(self.store)))
        if self.maxsize != 0:
            self.store[key] = value
        return value

    def __get__(self, obj: Any, owner: Any = None) -> Any:
        return self if obj is None else types.MethodType(self, obj)

    def cache_info(self) -> CacheInfo:
        return CacheInfo(self.hits, self.misses, self.maxsize, len(self.store))

    def cache_clear(self) -> None:
        self.store.clear()
        self.hits = self.misses = 0

    def __repr__(self) -> str:
        return f"<cached function {self.__name__}>"


def _functools(runner: Runner) -> dict[str, Any]:
    from mse_codezoo.interpreter import function

    def wraps(wrapped: Any) -> Callable[[Any], Any]:
        def decorate(wrapper: Any) -> Any:
            if isinstance(wrapper, function):
                wrapper.name = getattr(wrapped, "__name__", wrapper.name)
                wrapper.wrapped = wrapped
            return wrapper

        return decorate

    def cache(func: Any) -> Cached:
        return Cached(runner, func, None)

    def lru_cache(maxsize: Any = 128, typed: bool = False) -> Any:
        if callable(maxsize):
            return Cached(runner, maxsize, 128)
        return lambda func: Cached(runner, func, maxsize)

    return {
        "wraps": wraps,
        "cache": cache,
        "lru_cache": lru_cache,
        "reduce": functools.reduce,
        "partial": functools.partial,
    }


# --- itertools ---------------------------------------------------------------------------


def _itertools(runner: Runner) -> dict[str, Any]:
    lazy = runner._lazy

    def pool(values: Any) -> Any:
        """product() and friends keep all their inputs; endless ones would never end."""
        try:
            size = len(values)
        except TypeError:
            message = t("This needs a list or a range, not {what}.", what=describe(values))
            raise LearnerError(message, kind="type", exception=TypeError(message)) from None
        if size > MAX_ITEMS:
            raise LearnerError(t("That collection would hold far too many things for the zoo."))
        return values

    def batched(values: Any, n: int) -> Any:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError("n must be at least one")

        def chunks() -> Iterator[tuple[Any, ...]]:
            items = iter(values)
            while chunk := tuple(itertools.islice(items, n)):
                yield chunk

        return lazy("batched", chunks())

    names: dict[str, Any] = {
        "count": lambda start=0, step=1: lazy("count", itertools.count(start, step)),
        "cycle": lambda values: lazy("cycle", itertools.cycle(values)),
        "repeat": lambda value, *times: lazy("repeat", itertools.repeat(value, *times)),
        "islice": lambda values, *bounds: lazy("islice", itertools.islice(values, *bounds)),
        "chain": lambda *parts: lazy("chain", itertools.chain(*parts)),
        "accumulate": lambda values, *f, **k: lazy(
            "accumulate", itertools.accumulate(values, *f, **k)
        ),
        "takewhile": lambda f, values: lazy("takewhile", itertools.takewhile(f, values)),
        "dropwhile": lambda f, values: lazy("dropwhile", itertools.dropwhile(f, values)),
        "pairwise": lambda values: lazy("pairwise", itertools.pairwise(values)),
        "product": lambda *parts, repeat=1: lazy(
            "product", itertools.product(*(pool(p) for p in parts), repeat=repeat)
        ),
        "permutations": lambda values, r=None: lazy(
            "permutations", itertools.permutations(pool(values), r)
        ),
        "combinations": lambda values, r: lazy(
            "combinations", itertools.combinations(pool(values), r)
        ),
    }
    if runner.version >= NEWER_MODULE_NAMES[("itertools", "batched")]:
        names["batched"] = batched
    return names


# --- the rest of the modules ---------------------------------------------------------


def _math() -> dict[str, Any]:
    def guarded(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def check(*args: Any) -> Any:
            for arg in args:
                if isinstance(arg, int) and abs(arg) > MAX_FACTORIAL:
                    raise ValueError(f"numbers above {MAX_FACTORIAL} are too big here")
            return func(*args)

        return check

    names = {
        name: getattr(math, name)
        for name in (
            "pi",
            "e",
            "tau",
            "inf",
            "sqrt",
            "isqrt",
            "floor",
            "ceil",
            "trunc",
            "gcd",
            "fabs",
            "log",
            "log2",
            "log10",
            "exp",
            "sin",
            "cos",
            "tan",
            "hypot",
            "dist",
            "radians",
            "degrees",
            "isclose",
        )
    }
    names |= {name: guarded(getattr(math, name)) for name in ("factorial", "comb", "perm")}
    names["prod"] = lambda values, start=1: functools.reduce(
        lambda a, b: a * b, list(values)[:MAX_ITEMS], start
    )
    return names


def _random(runner: Runner) -> dict[str, Any]:
    rng = runner.random
    return {
        name: getattr(rng, name)
        for name in (
            "random",
            "randint",
            "randrange",
            "choice",
            "choices",
            "shuffle",
            "sample",
            "uniform",
            "seed",
        )
    }


def _copy(runner: Runner) -> dict[str, Any]:
    import copy

    def replace(obj: Any, /, **changes: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.replace(obj, **changes)
        if isinstance(obj, tuple) and hasattr(obj, "_replace"):
            return obj._replace(**changes)
        raise TypeError(f"replace() does not support {type(obj).__name__} objects")

    names: dict[str, Any] = {"copy": copy.copy, "deepcopy": copy.deepcopy}
    if runner.version >= NEWER_MODULE_NAMES[("copy", "replace")]:
        names["replace"] = replace
    return names


def _time(runner: Runner) -> dict[str, Any]:
    def sleep(seconds: Any) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, int | float) or seconds < 0:
            message = t("`sleep` needs a number of seconds, like `sleep(1)`.")
            raise LearnerError(message, kind="type", exception=ValueError(message))
        if runner.threads is not None and runner.threads.running:
            runner.pending = ("sleep", seconds)  # the thread waits after this line
            return
        if runner.loop is not None:  # time.sleep in async code: every task has to wait
            runner.events.append({"type": "block", "seconds": seconds})
        runner.clock += seconds

    def now() -> float:
        return float(runner.clock)

    return {"sleep": sleep, "time": now, "monotonic": now, "perf_counter": now}


def _dataclasses() -> dict[str, Any]:
    return {
        "dataclass": dataclasses.dataclass,
        "field": dataclasses.field,
        "asdict": dataclasses.asdict,
        "astuple": dataclasses.astuple,
        "replace": dataclasses.replace,
        "is_dataclass": dataclasses.is_dataclass,
        "FrozenInstanceError": dataclasses.FrozenInstanceError,
    }


def _typing() -> dict[str, Any]:
    names = (
        "NamedTuple",
        "Any",
        "Optional",
        "Union",
        "Callable",
        "Iterator",
        "Iterable",
        "Generator",
        "ClassVar",
        "Final",
        "Literal",
        "TypeVar",
        "Generic",
        "Protocol",
    )
    return {name: getattr(typing, name) for name in names}


def load(runner: Runner, name: str) -> module | None:
    """The zoo's version of a standard module, or ``None`` if it has none."""
    from mse_codezoo import scheduler

    makers: dict[str, Callable[[], dict[str, Any]]] = {
        "math": _math,
        "random": lambda: _random(runner),
        "functools": lambda: _functools(runner),
        "itertools": lambda: _itertools(runner),
        "dataclasses": _dataclasses,
        "typing": _typing,
        "copy": lambda: _copy(runner),
        "time": lambda: _time(runner),
        "json": lambda: {"dumps": json.dumps, "loads": json.loads},
        "string": lambda: {
            n: getattr(string, n)
            for n in (
                "ascii_letters",
                "ascii_lowercase",
                "ascii_uppercase",
                "digits",
                "punctuation",
            )
        },
        "asyncio": lambda: scheduler.asyncio_names(runner),
        "threading": lambda: scheduler.threading_names(runner),
        "__future__": lambda: {"annotations": True},
    }
    make = makers.get(name)
    if make is None:
        return None
    made = module(name, make())
    made.newer = {n: since for (m, n), since in NEWER_MODULE_NAMES.items() if m == name}
    return made
