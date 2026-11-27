"""The engine must import only the standard library (so it can run in Pyodide).

``cli.py`` is the one exception: it is the only module allowed to import click.
"""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / "mse_codezoo"
# voice.py: Piper is an optional add-on, imported only when a grown-up installed it
ALLOWED_THIRD_PARTY = {"cli.py": {"click"}, "voice.py": {"piper"}}


def imported_top_level_names(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


# learner programs in the levels run in our interpreter, not in Python; they may import
# the level's own helper files ("tricks", "burrow")
ENGINE = sorted(p for p in PACKAGE.rglob("*.py") if "content" not in p.parts)


@pytest.mark.parametrize("module", ENGINE, ids=lambda p: p.name)
def test_module_imports_only_stdlib(module: Path):
    allowed = set(sys.stdlib_module_names) | {"mse_codezoo", "__future__"}
    allowed |= ALLOWED_THIRD_PARTY.get(module.name, set())
    extra = imported_top_level_names(module) - allowed
    assert not extra, f"{module.name} imports non-stdlib modules: {sorted(extra)}"
