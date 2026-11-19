"""Level files and animal packs shipped in ``mse_codezoo/content``.

Standard library only: the engine must stay importable in Pyodide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mse_codezoo import ir
from mse_codezoo.goals import goal_errors
from mse_codezoo.i18n import LANGS, current
from mse_codezoo.lang_python import parse
from mse_codezoo.world import Pack, World

CONTENT_DIR = Path(__file__).parent / "content"
LEVELS_DIR = CONTENT_DIR / "levels"
ANIMALS_DIR = CONTENT_DIR / "animals"

REQUIRED_KEYS = ("id", "module", "concepts", "world", "goal")
DEFAULT_ANIMAL = "monkey"


class LevelError(Exception):
    """A level or pack cannot be found or loaded."""


@dataclass
class Level:
    id: str
    title: str
    module: str
    concepts: list[str]
    world: dict[str, Any]
    goal: dict[str, Any]
    constraints: dict[str, Any] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)
    unlocked_blocks: list[str] = field(default_factory=list)
    mode: str = "blocks_only"
    animal: str = DEFAULT_ANIMAL
    starter: str = ""  # program the level opens with (e.g. a broken one to fix)
    variants: list[dict[str, Any]] = field(default_factory=list)  # more worlds to solve
    i18n: dict[str, dict[str, Any]] = field(default_factory=dict)  # lang -> title, hints
    path: Path | None = None

    def _text(self, key: str, default: Any) -> Any:
        return self.i18n.get(current(), {}).get(key) or default

    @property
    def shown_title(self) -> str:
        """The title in the current language."""
        return self._text("title", self.title)

    @property
    def shown_hints(self) -> list[str]:
        return list(self._text("hints", self.hints))

    def worlds(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """(world spec, goal) for the main world and every variant."""
        out = [(self.world, self.goal)]
        for variant in self.variants:
            spec = {key: value for key, value in variant.items() if key != "goal"}
            out.append((spec, variant.get("goal", self.goal)))
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path | None = None) -> Level:
        return cls(
            id=data["id"],
            title=data.get("title", data["id"]),
            module=data["module"],
            concepts=list(data["concepts"]),
            world=data["world"],
            goal=data["goal"],
            constraints=dict(data.get("constraints", {})),
            hints=list(data.get("hints", [])),
            unlocked_blocks=list(data.get("unlockedBlocks", [])),
            mode=data.get("mode", "blocks_only"),
            animal=data.get("animal", DEFAULT_ANIMAL),
            starter=data.get("starter", ""),
            variants=list(data.get("variants", [])),
            i18n=dict(data.get("i18n", {})),
            path=path,
        )


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


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LevelError(f"cannot read {path.name}: {exc}") from None


def load_level(path: Path) -> Level:
    data = _read_json(path)
    if not isinstance(data, dict) or any(key not in data for key in REQUIRED_KEYS):
        raise LevelError(f"{path.name} is not a valid level; run `codezoo levels validate`")
    return Level.from_dict(data, path)


def find_level(ref: str, root: Path = LEVELS_DIR) -> Level:
    """Load a level by file path or by id (``m01-l01``)."""
    path = Path(ref)
    if path.suffix == ".json" and path.is_file():
        return load_level(path)
    for candidate in level_files(root):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("id") == ref:
            return load_level(candidate)
    raise LevelError(f"No level called {ref!r}. Try `codezoo levels list`.")


def load_pack(name: str, root: Path = ANIMALS_DIR) -> Pack:
    path = root / name / "pack.json"
    if not path.is_file():
        raise LevelError(f"No animal pack called {name!r}.")
    return Pack.from_dict(_read_json(path))


def validate_level(path: Path) -> LevelReport:
    """Structural checks: JSON shape, world, goal, constraints, reference solution file.

    Running the reference solution is done by ``game.solution_errors``.
    """
    report = LevelReport(path)
    try:
        data = _read_json(path)
    except LevelError as exc:
        report.errors.append(str(exc))
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
    if missing:
        return report

    try:
        world = World.from_spec(data["world"])
    except (ValueError, TypeError) as exc:
        report.errors.append(f"world: {exc}")
        world = None
    report.errors += goal_errors(data["goal"], world)

    variants = data.get("variants", [])
    if not isinstance(variants, list):
        report.errors.append("variants must be a list of worlds")
        variants = []
    for number, variant in enumerate(variants, 2):
        if not isinstance(variant, dict):
            report.errors.append(f"variant {number}: must be a world object")
            continue
        try:
            other = World.from_spec(variant)
        except (ValueError, TypeError) as exc:
            report.errors.append(f"variant {number}: {exc}")
            other = None
        errors = goal_errors(variant.get("goal", data["goal"]), other)
        report.errors += [f"variant {number}: {error}" for error in errors]

    translations = data.get("i18n", {})
    hints = data.get("hints", [])
    for lang, text in translations.items() if isinstance(translations, dict) else []:
        if lang not in LANGS:
            report.errors.append(f"i18n: unknown language {lang!r}")
        elif not isinstance(text, dict):
            report.errors.append(f"i18n.{lang} must be an object")
        elif "hints" in text and len(text["hints"]) != len(hints):
            report.errors.append(f"i18n.{lang}.hints must have {len(hints)} hint(s)")

    constraints = data.get("constraints", {})
    max_lines = constraints.get("maxLines")
    if max_lines is not None and (not isinstance(max_lines, int) or max_lines < 1):
        report.errors.append("constraints.maxLines must be a positive whole number")
    unknown = [n for n in constraints.get("mustUse", []) if n not in ir.NODE_TYPES]
    if unknown:
        report.errors.append(f"constraints.mustUse has unknown node types: {', '.join(unknown)}")

    starter = data.get("starter", "")
    if not isinstance(starter, str):
        report.errors.append("starter must be Python code as text")
    elif starter and not parse(starter).ok:
        report.errors.append("starter is not valid Python")

    animal = data.get("animal", DEFAULT_ANIMAL)
    if not (ANIMALS_DIR / animal / "pack.json").is_file():
        report.errors.append(f"unknown animal {animal!r}")
    return report
