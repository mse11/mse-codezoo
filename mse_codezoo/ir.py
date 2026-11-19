"""Language-neutral program model (IR).

Blocks, code and the running animal all point at the same nodes through stable ids.
The JSON form (``to_dict`` / ``from_dict``) is the contract with the web client.
Standard library only.
"""

from __future__ import annotations

import itertools
import types
import typing
from collections.abc import Iterator
from dataclasses import MISSING, dataclass, field, fields
from typing import Any

IR_VERSION = 1  # bump when the JSON shape changes in a way old clients can't read


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
class Call(Expr):
    func: str
    args: list[Expr] = field(default_factory=list)


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
    target: Name
    value: Expr


@dataclass(kw_only=True)
class AugAssign(Stmt):
    target: Name
    op: str
    value: Expr


@dataclass(kw_only=True)
class For(Stmt):
    target: Name
    iter: Expr
    body: list[Stmt] = field(default_factory=list)


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
        BinOp,
        UnaryOp,
        ExprStmt,
        Assign,
        AugAssign,
        For,
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
ABSTRACT_TYPES: dict[str, type[Node]] = {"Expr": Expr, "Stmt": Stmt}


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
    doc = (cls.__doc__ or "").strip()
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
