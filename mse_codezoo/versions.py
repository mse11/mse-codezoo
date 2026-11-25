"""Python releases: which syntax and builtins arrived when, and what this computer can read.

The course is written for Python 3.11; every newer release gets a "release island" of
levels. A program is checked against the release it is set to, so the message can name
the release that brought something newer. Syntax can only be read by a computer whose own
Python is at least that new (``HOST``); newer islands show as locked there.
Standard library only.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass

BASELINE = (3, 11)
NEWEST = (3, 15)
RELEASES = [(3, 11), (3, 12), (3, 13), (3, 14), (3, 15)]
HOST = (sys.version_info.major, sys.version_info.minor)
DEFAULT = min(HOST, NEWEST)  # programs may use everything this computer can read

NEWER_BUILTINS: dict[str, tuple[int, int]] = {"frozendict": (3, 15), "sentinel": (3, 15)}
NEWER_MODULE_NAMES: dict[tuple[str, str], tuple[int, int]] = {
    ("itertools", "batched"): (3, 12),
    ("copy", "replace"): (3, 13),
    ("concurrent", "interpreters"): (3, 14),
}


def version_text(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def parse_version(text: str | None) -> tuple[int, int] | None:
    """``"3.12"`` -> ``(3, 12)``; ``None`` or ``""`` -> ``None``. Raises ``ValueError``."""
    if not text:
        return None
    try:
        major, minor = (int(part) for part in str(text).split("."))
    except ValueError:
        raise ValueError(f"not a Python version: {text!r}") from None
    version = (major, minor)
    if version not in RELEASES:
        known = ", ".join(version_text(v) for v in RELEASES)
        raise ValueError(f"CodeZoo knows Python {known}, not {text}")
    return version


def readable(version: tuple[int, int]) -> bool:
    """Whether this computer's Python can read programs written for ``version``."""
    return version <= HOST


# what newer_syntax() calls each feature (translated where it is shown)
NEWER_FEATURES = (
    "`type` statements",
    "type parameters like `[T]`",
    'template strings (`t"..."`)',
    "f-strings with the same quotes inside",
    "`except A, B:` without brackets",
    "`*` in front of a comprehension's item",
    "`lazy import`",
)


@dataclass
class Newer:
    """A piece of syntax that arrived after the release a program is set to."""

    line: int
    col: int
    what: str
    since: tuple[int, int]


def newer_syntax(tree: ast.AST, text: str) -> list[Newer]:
    """Syntax in ``tree`` that a Python older than 3.15 can't read, with its release."""
    found: list[Newer] = []
    lines = text.splitlines()

    def add(node: ast.AST, what: str, since: tuple[int, int]) -> None:
        found.append(Newer(getattr(node, "lineno", 1), getattr(node, "col_offset", 0), what, since))

    for node in ast.walk(tree):
        name = type(node).__name__
        if name == "TypeAlias":
            add(node, "`type` statements", (3, 12))
        elif getattr(node, "type_params", None):
            add(node, "type parameters like `[T]`", (3, 12))
        elif name == "TemplateStr":
            add(node, 'template strings (`t"..."`)', (3, 14))
        elif isinstance(node, ast.JoinedStr) and _nested_fstring(node, text):
            add(node, "f-strings with the same quotes inside", (3, 12))
        elif isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Tuple):
            line = lines[node.lineno - 1][node.col_offset :] if node.lineno <= len(lines) else ""
            after = line.removeprefix("except").lstrip(" *")
            if not after.startswith("("):
                add(node, "`except A, B:` without brackets", (3, 14))
        elif isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp) and isinstance(
            node.elt, ast.Starred
        ):
            add(node, "`*` in front of a comprehension's item", (3, 15))
        elif isinstance(node, ast.Import | ast.ImportFrom) and getattr(node, "is_lazy", False):
            add(node, "`lazy import`", (3, 15))
    return sorted(found, key=lambda n: (n.line, n.col))


def _nested_fstring(node: ast.JoinedStr, text: str) -> bool:
    """An f-string that reuses its own quote (or a backslash) inside ``{...}`` (PEP 701)."""
    segment = ast.get_source_segment(text, node) or ""
    body = segment.lstrip("rRfFbBuU")
    if not body or body.startswith(('"""', "'''")):
        return False
    quote = body[0]
    for part in node.values:
        if isinstance(part, ast.FormattedValue):
            inner = ast.get_source_segment(text, part.value) or ""
            if quote in inner or "\\" in inner:
                return True
    return False


TEMPLATE_STRING = re.compile(r"(?<![\w\"'])[tT][rR]?[\"']")
LAZY_IMPORT = re.compile(r"^\s*lazy\s+(import|from)\s", re.MULTILINE)
TYPE_STATEMENT = re.compile(r"^\s*type\s+\w+(\[[^\]]*\])?\s*=", re.MULTILINE)
TYPE_PARAMS = re.compile(r"^\s*(def|class)\s+\w+\[", re.MULTILINE)


def host_hint(text: str) -> tuple[str, tuple[int, int]] | None:
    """When this computer can't read a program: a guess at the newer syntax it uses."""
    if HOST < (3, 12) and TYPE_STATEMENT.search(text):
        return "`type` statements", (3, 12)
    if HOST < (3, 12) and TYPE_PARAMS.search(text):
        return "type parameters like `[T]`", (3, 12)
    if HOST < (3, 14) and TEMPLATE_STRING.search(text):
        return 'template strings (`t"..."`)', (3, 14)
    if HOST < (3, 15) and LAZY_IMPORT.search(text):
        return "`lazy import`", (3, 15)
    return None
