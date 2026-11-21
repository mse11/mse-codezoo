"""Level files and animal packs shipped in ``mse_codezoo/content``.

Standard library only: the engine must stay importable in Pyodide.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mse_codezoo import ir
from mse_codezoo.goals import PSEUDO_CONCEPTS, goal_errors
from mse_codezoo.i18n import LANGS, current
from mse_codezoo.lang_python import parse
from mse_codezoo.versions import parse_version, readable
from mse_codezoo.world import TERRAIN, TRICKS, Pack, World

CONTENT_DIR = Path(__file__).parent / "content"
LEVELS_DIR = CONTENT_DIR / "levels"
ANIMALS_DIR = CONTENT_DIR / "animals"

REQUIRED_KEYS = ("id", "module", "concepts", "world", "goal")
DEFAULT_ANIMAL = "monkey"


# `{B}`, `{B.few}`, `{B.many}` in a title or hint: the item on tile B, named by the animal
# that plays, in the current language (`few` and `many` are the plural forms of the pack)
ITEM_PLACEHOLDER = re.compile(r"\{([A-Z])(?:\.(one|few|many))?\}")


def fill_items(text: str, pack: Pack) -> str:
    """Put the animal's own item names into a title or hint: "One {B}" -> "One flower"."""

    def name(match: re.Match[str]) -> str:
        tile, form = match[1], match[2] or "one"
        forms = pack._names().get("items", {}).get(tile)
        if not forms:
            item = pack.item_name(tile)
            forms = {"one": item, "many": item if item.endswith("s") else item + "s"}
        if form == "few":
            return forms.get("few") or forms.get("many") or forms["one"]
        return forms.get(form) or forms["one"]

    filled = ITEM_PLACEHOLDER.sub(name, text)
    if text.startswith("{") and filled:
        filled = filled[0].upper() + filled[1:]
    return filled


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
    signature: bool = False  # uses the animal's own tricks, so only that animal plays it
    files: dict[str, str] = field(default_factory=dict)  # helper files: {"tricks": "def ..."}
    i18n: dict[str, dict[str, Any]] = field(default_factory=dict)  # lang -> title, hints
    min_python: tuple[int, int] | None = None  # a release island: "minPython": "3.12"
    path: Path | None = None

    def _text(self, key: str, default: Any) -> Any:
        return self.i18n.get(current(), {}).get(key) or default

    @property
    def shown_title(self) -> str:
        """The title in the current language, for the level's own animal."""
        return self.title_for(None)

    @property
    def shown_hints(self) -> list[str]:
        return [fill_items(h, load_pack(self.animal)) for h in self._text("hints", self.hints)]

    def title_for(self, animal: str | None) -> str:
        """The title in the current language, with the items of ``animal`` (if it can play
        the level; else of the level's own animal)."""
        name = animal if animal and not self.signature else self.animal
        try:
            pack = load_pack(name)
        except LevelError:
            pack = load_pack(self.animal)
        return fill_items(self._text("title", self.title), pack)

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
            signature=bool(data.get("signature", False)),
            files=dict(data.get("files", {})),
            i18n=dict(data.get("i18n", {})),
            min_python=parse_version(data.get("minPython")),
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
    return validate_level_data(data, report, has_solution=solution_path(path).is_file())


def validate_level_data(
    data: Any, report: LevelReport | None = None, *, has_solution: bool = True
) -> LevelReport:
    """The structural checks of ``validate_level`` for a level given as data."""
    report = report or LevelReport(Path("level.json"))
    path = report.path
    if not isinstance(data, dict):
        report.errors.append("level must be a JSON object")
        return report
    report.level_id = data.get("id")
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        report.errors.append(f"missing keys: {', '.join(missing)}")
    if not has_solution:
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
    unknown = [
        n
        for n in constraints.get("mustUse", [])
        if n not in ir.NODE_TYPES and n not in PSEUDO_CONCEPTS
    ]
    if unknown:
        report.errors.append(f"constraints.mustUse has unknown node types: {', '.join(unknown)}")

    try:
        need = parse_version(data.get("minPython"))
    except ValueError as exc:
        report.errors.append(f"minPython: {exc}")
        need = None
    if need is not None and not readable(need):
        return report  # this computer's Python can't read the island's code

    starter = data.get("starter", "")
    if not isinstance(starter, str):
        report.errors.append("starter must be Python code as text")
    elif starter and not parse(starter).ok:
        report.errors.append("starter is not valid Python")

    animal = data.get("animal", DEFAULT_ANIMAL)
    if not (ANIMALS_DIR / animal / "pack.json").is_file():
        report.errors.append(f"unknown animal {animal!r}")
        return report
    files = data.get("files", {})
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and k.isidentifier() and isinstance(v, str) and parse(v).ok
        for k, v in files.items()
    ):
        report.errors.append('files must map a helper name to valid Python: {"tricks": "..."}')
    if not data.get("signature"):
        # a core level is re-skinned for every animal, so it may use only the shared world
        uses = [
            tile
            for spec in [data["world"], *[v for v in variants if isinstance(v, dict)]]
            for row in _rows(spec)
            for tile in row
            if tile in TERRAIN
        ]
        if uses or any(block in TRICKS for block in data.get("unlockedBlocks", [])):
            report.errors.append(
                'uses terrain or tricks, so it must be a signature level ("signature": true)'
            )
    return report


def core_animals(level: Level) -> list[str]:
    """Animals that can play ``level``: only its own for a signature level, else all."""
    if level.signature:
        return [level.animal]
    return animal_names()


def animal_names(root: Path = ANIMALS_DIR) -> list[str]:
    names = sorted(p.parent.name for p in root.glob("*/pack.json"))
    return [DEFAULT_ANIMAL, *[n for n in names if n != DEFAULT_ANIMAL]]


def _rows(spec: dict[str, Any]) -> list[str]:
    tiles = spec.get("tiles")
    if isinstance(tiles, str):
        return tiles.split("\n")
    return [row for row in tiles if isinstance(row, str)] if isinstance(tiles, list) else []
