"""Find and validate level files shipped in ``mse_codezoo/content/levels``.

Standard library only: the engine must stay importable in Pyodide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

LEVELS_DIR = Path(__file__).parent / "content" / "levels"

REQUIRED_KEYS = ("id", "module", "concepts", "world", "goal")


@dataclass
class LevelReport:
    path: Path
    level_id: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def level_files(root: Path = LEVELS_DIR) -> list[Path]:
    """All level JSON files under ``root``, sorted for stable output."""
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.json"))


def solution_path(level_path: Path) -> Path:
    """``l03.json`` -> ``l03.solution.py`` next to it."""
    return level_path.with_name(f"{level_path.stem}.solution.py")


def validate_level(path: Path) -> LevelReport:
    """Check the file is a JSON object with the required keys and a reference solution.

    Running the reference solution is added once the interpreter exists.
    """
    report = LevelReport(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.errors.append(f"cannot read JSON: {exc}")
        return report
    if not isinstance(data, dict):
        report.errors.append("level must be a JSON object")
        return report
    report.level_id = data.get("id")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        report.errors.append(f"missing keys: {', '.join(missing)}")
    if not solution_path(path).is_file():
        report.errors.append(f"missing reference solution {solution_path(path).name}")
    return report
