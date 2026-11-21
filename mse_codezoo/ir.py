"""Language-neutral program model (IR).

Blocks, code and the running animal all point at the same nodes through stable ids.
The JSON form (``to_dict`` / ``from_dict``) is the contract with the web client.
Standard library only.
"""

from __future__ import annotations

import inspect
import itertools
import types
import typing
from collections.abc import Iterator
from dataclasses import MISSING, dataclass, field, fields
from typing import Any

IR_VERSION = 4  # bump when the JSON shape changes in a way old clients can't read


@dataclass(kw_only=True)
class Node:
    id: str = ""


@dataclass(kw_only=True)
class Expr(Node):
    """Something that has a value."""


@dataclass(kw_only=True)
class Stmt(Node):
    """One instruction; compound statements have a body."""

    comment: str | None = None  # inline comment after the statement's first line


# --- expressions -----------------------------------------------------------


@dataclass(kw_only=True)
class Const(Expr):
    value: int | float | str | bool | None


@dataclass(kw_only=True)
class Name(Expr):
    name: str


@dataclass(kw_only=True)
class Keyword(Node):
    """A named argument, like ``end=""`` in ``print(x, end="")``; a ``name`` of ``None``
    is a ``**options`` merge."""

    name: str | None
    value: Expr


@dataclass(kw_only=True)
class Call(Expr):
    func: str
    args: list[Expr] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)


@dataclass(kw_only=True)
class MethodCall(Expr):
    """A method on a value, like ``name.upper()`` or ``logs.sort(reverse=True)``."""

    obj: Expr
    method: str
    args: list[Expr] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)


@dataclass(kw_only=True)
class Attribute(Expr):
    """A name inside a module: ``tricks.HEIGHT``."""

    value: Expr
    attr: str


@dataclass(kw_only=True)
class List(Expr):
    elts: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Tuple(Expr):
    elts: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Set(Expr):
    elts: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Dict(Expr):
    """``{"oak": 3, **other}``: a key of ``None`` marks a ``**`` merge of ``values[i]``."""

    keys: list[Expr | None] = field(default_factory=list)
    values: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Starred(Expr):
    """``*rest`` in ``first, *rest = logs`` or ``[*a, *b]``."""

    value: Expr


@dataclass(kw_only=True)
class CompFor(Node):
    """One ``for target in iter if ...`` part of a comprehension."""

    target: Expr
    iter: Expr
    ifs: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Comprehension(Expr):
    """``[elt for ...]`` (kind ``list``), ``{elt for ...}`` (``set``),
    ``{elt: value for ...}`` (``dict``) or ``(elt for ...)`` (``generator``)."""

    kind: str
    elt: Expr
    value: Expr | None = None
    generators: list[CompFor] = field(default_factory=list)


@dataclass(kw_only=True)
class Param(Node):
    """One input of a function, with an optional default: ``height=2``.

    ``kind`` is ``plain``, ``args`` (``*args``), ``kwargs`` (``**kwargs``) or ``kwonly``
    (after ``*``). ``annotation`` is a type hint, kept as written and never run."""

    name: str
    default: Expr | None = None
    kind: str = "plain"
    annotation: Expr | None = None


@dataclass(kw_only=True)
class Lambda(Expr):
    """``lambda log: log.length``"""

    params: list[Param] = field(default_factory=list)
    body: Expr


@dataclass(kw_only=True)
class Yield(Expr):
    """``yield drop``: hand one value out and pause until asked for the next."""

    value: Expr | None = None


@dataclass(kw_only=True)
class YieldFrom(Expr):
    """``yield from nectar()``: hand out every value of another generator."""

    value: Expr


@dataclass(kw_only=True)
class Await(Expr):
    """``await reach(3)``: wait here; other tasks run meanwhile."""

    value: Expr


@dataclass(kw_only=True)
class TString(Expr):
    """A template string ``t"..."`` (Python 3.14): text parts and ``FormattedValue`` parts."""

    parts: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Compare(Expr):
    """``a < b``, also chained: ``1 < x < 3`` has two ops and two comparators."""

    left: Expr
    ops: list[str]
    comparators: list[Expr]


@dataclass(kw_only=True)
class BoolOp(Expr):
    """``and`` / ``or`` over two or more values."""

    op: str
    values: list[Expr]


@dataclass(kw_only=True)
class IfExp(Expr):
    """``body if test else orelse``"""

    test: Expr
    body: Expr
    orelse: Expr


@dataclass(kw_only=True)
class FormattedValue(Expr):
    """One ``{value!r:>5}`` part of an f-string."""

    value: Expr
    conversion: str | None = None  # "r", "s" or "a"
    spec: str | None = None


@dataclass(kw_only=True)
class FString(Expr):
    """An f-string: text parts (``Const``) and ``FormattedValue`` parts."""

    parts: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Slice(Expr):
    """``lower:upper:step`` inside ``[...]``; any part may be missing."""

    lower: Expr | None = None
    upper: Expr | None = None
    step: Expr | None = None


@dataclass(kw_only=True)
class Subscript(Expr):
    """Indexing or slicing: ``text[0]``, ``text[1:3]``."""

    value: Expr
    index: Expr


@dataclass(kw_only=True)
class BinOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(kw_only=True)
class UnaryOp(Expr):
    op: str
    operand: Expr


# --- statements --------------------------------------------------------------


@dataclass(kw_only=True)
class ExprStmt(Stmt):
    value: Expr


@dataclass(kw_only=True)
class Assign(Stmt):
    """``target = value``; the target is a ``Name``, a ``Subscript`` (``inv["oak"] = 3``)
    or a ``Tuple`` of them (``a, b = b, a``)."""

    target: Expr
    value: Expr


@dataclass(kw_only=True)
class AugAssign(Stmt):
    """``x += 1`` or ``inv["oak"] += 1``."""

    target: Expr
    op: str
    value: Expr


@dataclass(kw_only=True)
class For(Stmt):
    """``for target in iter:``; the target is a ``Name`` or a ``Tuple`` of names."""

    target: Expr
    iter: Expr
    body: list[Stmt] = field(default_factory=list)


@dataclass(kw_only=True)
class If(Stmt):
    """``if`` / ``else``. An ``elif`` is an ``If`` that is the only statement in ``orelse``."""

    test: Expr
    body: list[Stmt] = field(default_factory=list)
    orelse: list[Stmt] = field(default_factory=list)


@dataclass(kw_only=True)
class While(Stmt):
    test: Expr
    body: list[Stmt] = field(default_factory=list)


@dataclass(kw_only=True)
class Break(Stmt):
    pass


@dataclass(kw_only=True)
class Continue(Stmt):
    pass


@dataclass(kw_only=True)
class FunctionDef(Stmt):
    """``def`` (or ``async def``), with decorators applied from the bottom up."""

    name: str
    params: list[Param] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
    decorators: list[Expr] = field(default_factory=list)
    is_async: bool = False
    returns: Expr | None = None
    type_params: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class ClassDef(Stmt):
    """``class Worker(Bee):``"""

    name: str
    bases: list[Expr] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
    decorators: list[Expr] = field(default_factory=list)
    type_params: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class AnnAssign(Stmt):
    """``length: float = 2.5``; the type hint is kept as written and never run."""

    target: Expr
    annotation: Expr
    value: Expr | None = None


@dataclass(kw_only=True)
class WithItem(Node):
    """``open("log.txt") as file`` in a ``with``; ``target`` may be missing."""

    context: Expr
    target: Expr | None = None


@dataclass(kw_only=True)
class With(Stmt):
    """``with a, b as c:`` (or ``async with``): everything is put back afterwards."""

    items: list[WithItem] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
    is_async: bool = False


@dataclass(kw_only=True)
class Nonlocal(Stmt):
    names: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class TypeAlias(Stmt):
    """``type Stack = list[int]`` (Python 3.12)."""

    name: str
    type_params: list[str] = field(default_factory=list)
    value: Expr


@dataclass(kw_only=True)
class Pattern(Node):
    """One shape a ``case`` can match."""


@dataclass(kw_only=True)
class PatternValue(Pattern):
    """A literal or a dotted name: ``case "paw":``, ``case None:``."""

    value: Expr


@dataclass(kw_only=True)
class PatternCapture(Pattern):
    """``case size:`` catches anything into ``size``; a ``name`` of ``None`` is ``_``."""

    name: str | None = None


@dataclass(kw_only=True)
class PatternSequence(Pattern):
    """``case ("paw", size):`` or ``case [first, *rest]:``."""

    patterns: list[Pattern] = field(default_factory=list)


@dataclass(kw_only=True)
class PatternStar(Pattern):
    """``*rest`` inside a sequence pattern."""

    name: str | None = None


@dataclass(kw_only=True)
class PatternOr(Pattern):
    """``case "paw" | "claw":``"""

    patterns: list[Pattern] = field(default_factory=list)


@dataclass(kw_only=True)
class PatternAs(Pattern):
    """``case ("paw", _) as print:``"""

    pattern: Pattern
    name: str


@dataclass(kw_only=True)
class PatternMapping(Pattern):
    """``case {"kind": "paw", **rest}:``"""

    keys: list[Expr] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    rest: str | None = None


@dataclass(kw_only=True)
class PatternClass(Pattern):
    """``case Footprint(kind="paw", size=s):``"""

    cls: Expr
    patterns: list[Pattern] = field(default_factory=list)
    kwd_names: list[str] = field(default_factory=list)
    kwd_patterns: list[Pattern] = field(default_factory=list)


@dataclass(kw_only=True)
class MatchCase(Node):
    pattern: Pattern
    guard: Expr | None = None
    body: list[Stmt] = field(default_factory=list)


@dataclass(kw_only=True)
class Match(Stmt):
    """``match footprint:`` with its ``case`` parts."""

    subject: Expr
    cases: list[MatchCase] = field(default_factory=list)


@dataclass(kw_only=True)
class Return(Stmt):
    value: Expr | None = None


@dataclass(kw_only=True)
class Global(Stmt):
    names: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class ExceptHandler(Node):
    """``except kind as name:``; ``kind`` is a name, a ``Tuple`` of names or ``None``."""

    kind: Expr | None = None
    name: str | None = None
    body: list[Stmt] = field(default_factory=list)


@dataclass(kw_only=True)
class Try(Stmt):
    """``try`` / ``except``; ``star`` marks ``except*`` for exception groups."""

    body: list[Stmt] = field(default_factory=list)
    handlers: list[ExceptHandler] = field(default_factory=list)
    orelse: list[Stmt] = field(default_factory=list)
    finalbody: list[Stmt] = field(default_factory=list)
    star: bool = False


@dataclass(kw_only=True)
class Raise(Stmt):
    """``raise CrackError("thin ice")``, or a bare ``raise`` inside ``except``."""

    exc: Expr | None = None


@dataclass(kw_only=True)
class Assert(Stmt):
    test: Expr
    msg: Expr | None = None


@dataclass(kw_only=True)
class Delete(Stmt):
    targets: list[Expr] = field(default_factory=list)


@dataclass(kw_only=True)
class Import(Stmt):
    """``import tricks`` (no ``names``) or ``from tricks import climb_tree, HEIGHT``;
    ``lazy`` marks ``lazy import`` (Python 3.15)."""

    module: str
    names: list[str] = field(default_factory=list)
    lazy: bool = False


@dataclass(kw_only=True)
class Pass(Stmt):
    pass


@dataclass(kw_only=True)
class Comment(Stmt):
    text: str


@dataclass(kw_only=True)
class RawCode(Stmt):
    """Code CodeZoo cannot show as blocks yet. Kept verbatim, never dropped."""

    text: str
    reason: str


@dataclass(kw_only=True)
class Program(Node):
    body: list[Stmt] = field(default_factory=list)


NODE_TYPES: dict[str, type[Node]] = {
    cls.__name__: cls
    for cls in (
        Const,
        Name,
        Call,
        Keyword,
        MethodCall,
        Attribute,
        List,
        Tuple,
        Set,
        Dict,
        Starred,
        CompFor,
        Comprehension,
        Lambda,
        Yield,
        YieldFrom,
        Await,
        TString,
        BinOp,
        UnaryOp,
        Compare,
        BoolOp,
        IfExp,
        FormattedValue,
        FString,
        Slice,
        Subscript,
        ExprStmt,
        Assign,
        AugAssign,
        For,
        If,
        While,
        Break,
        Continue,
        Param,
        FunctionDef,
        ClassDef,
        AnnAssign,
        WithItem,
        With,
        Nonlocal,
        TypeAlias,
        PatternValue,
        PatternCapture,
        PatternSequence,
        PatternStar,
        PatternOr,
        PatternAs,
        PatternMapping,
        PatternClass,
        MatchCase,
        Match,
        Return,
        Global,
        ExceptHandler,
        Try,
        Raise,
        Assert,
        Delete,
        Import,
        Pass,
        Comment,
        RawCode,
        Program,
    )
}


class Ids:
    """Hands out node ids: n1, n2, ..."""

    def __init__(self, prefix: str = "n") -> None:
        self._count = itertools.count(1)
        self._prefix = prefix

    def __call__(self) -> str:
        return f"{self._prefix}{next(self._count)}"


def walk(node: Node) -> Iterator[Node]:
    """Every node in the tree, depth first, parents before children."""
    yield node
    for f in fields(node):
        value = getattr(node, f.name)
        if isinstance(value, Node):
            yield from walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Node):
                    yield from walk(item)


def to_dict(node: Node, *, ids: bool = True) -> dict[str, Any]:
    """JSON-ready dict. ``ids=False`` gives the shape only, for comparing programs."""
    data: dict[str, Any] = {"type": type(node).__name__}
    for f in fields(node):
        value = getattr(node, f.name)
        if (f.name == "id" and not ids) or (f.name == "comment" and value is None):
            continue
        data[f.name] = _dump(value, ids)
    return data


def _dump(value: Any, ids: bool) -> Any:
    if isinstance(value, Node):
        return to_dict(value, ids=ids)
    if isinstance(value, list):
        return [_dump(item, ids) for item in value]
    return value


def from_dict(data: dict[str, Any]) -> Node:
    cls = NODE_TYPES.get(data.get("type", ""))
    if cls is None:
        raise ValueError(f"unknown node type {data.get('type')!r}")
    return cls(**{key: _load(value) for key, value in data.items() if key != "type"})


def _load(value: Any) -> Any:
    if isinstance(value, dict) and "type" in value:
        return from_dict(value)
    if isinstance(value, list):
        return [_load(item) for item in value]
    return value


# --- JSON schema ---------------------------------------------------------------

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
ABSTRACT_TYPES: dict[str, type[Node]] = {"Expr": Expr, "Stmt": Stmt, "Pattern": Pattern}


def json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) for a serialised ``Program``, generated from the dataclasses.

    This is the contract with the web client; ``mse_codezoo/ir.schema.json`` is a copy
    kept in sync by the tests.
    """
    defs: dict[str, Any] = {}
    for name, base in ABSTRACT_TYPES.items():
        members = [n for n, cls in NODE_TYPES.items() if issubclass(cls, base)]
        defs[name] = {"oneOf": [{"$ref": f"#/$defs/{n}"} for n in members]}
    for name, cls in NODE_TYPES.items():
        defs[name] = _node_schema(name, cls)
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": f"urn:mse-codezoo:ir:v{IR_VERSION}",
        "title": "CodeZoo program (IR)",
        "description": (
            f"IR version {IR_VERSION}. Generated from mse_codezoo/ir.py by `codezoo schema`; "
            "do not edit by hand."
        ),
        "$ref": "#/$defs/Program",
        "$defs": defs,
    }


def _node_schema(name: str, cls: type[Node]) -> dict[str, Any]:
    hints = typing.get_type_hints(cls)
    properties: dict[str, Any] = {"type": {"const": name}}
    required = ["type", "id"]
    for f in fields(cls):
        properties[f.name] = _type_schema(hints[f.name])
        if f.name == "id":
            properties["id"]["minLength"] = 1  # every serialised node has an id
        no_default = f.default is MISSING and f.default_factory is MISSING
        if no_default and f.name not in required:
            required.append(f.name)
    # Python 3.13+ strips docstring indentation itself; cleandoc gives the same text on 3.11
    doc = inspect.cleandoc(cls.__doc__ or "")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if doc and not doc.startswith(f"{name}("):  # skip the dataclass-generated signature
        schema = {"description": doc, **schema}
    return schema


JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}


def _type_schema(hint: Any) -> dict[str, Any]:
    origin = typing.get_origin(hint)
    if origin is list:
        (item,) = typing.get_args(hint)
        return {"type": "array", "items": _type_schema(item)}
    if origin in (types.UnionType, typing.Union):
        options = typing.get_args(hint)
        if all(option in JSON_TYPES for option in options):
            names = [JSON_TYPES[option] for option in options]
            if "number" in names and "integer" in names:
                names.remove("integer")  # JSON numbers include integers
            return {"type": names}
        return {"anyOf": [_type_schema(option) for option in options]}
    if hint in JSON_TYPES:
        return {"type": JSON_TYPES[hint]}
    if isinstance(hint, type) and issubclass(hint, Node):
        return {"$ref": f"#/$defs/{hint.__name__}"}
    raise TypeError(f"no JSON schema for {hint!r}")
