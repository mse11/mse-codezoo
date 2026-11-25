"""Play one level: parse the learner's code, run it in the world, check the goal.

A level may have several worlds (``variants``): the program runs in the one being shown,
then quietly in all the others, and the level is solved only when it works everywhere.
That is what makes ``if`` worth learning. Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mse_codezoo import interpreter, ir, versions
from mse_codezoo.feelings import Feeling, feeling
from mse_codezoo.goals import CheckResult, check, goal_met
from mse_codezoo.i18n import t
from mse_codezoo.interpreter import RunResult, Step
from mse_codezoo.lang_python import ParseResult, parse, print_program
from mse_codezoo.levels import Level, core_animals, fill_items, load_pack, solution_path
from mse_codezoo.profiles import Attempt, classify_mistakes
from mse_codezoo.world import Pack, World

OnStep = Callable[[Step, World, ParseResult], None]


@dataclass
class LevelRun:
    level: Level
    parsed: ParseResult
    world: World | None = None
    result: RunResult | None = None
    check: CheckResult | None = None
    variant: int = 0  # which world was shown: 0 = the main one
    feeling: Feeling | None = None
    animal: str = ""
    version: tuple[int, int] = versions.DEFAULT
    locked: str | None = None  # why the level can't be played here

    def line_of(self, node_id: str | None) -> int | None:
        span = self.parsed.positions.get(node_id or "")
        return span.line if span else None

    @property
    def error_kind(self) -> str | None:
        if not self.parsed.ok:
            return "syntax"
        if self.result is not None and self.result.error is not None:
            return self.result.error.kind
        return None


Modules = dict[str, str]


def pick_animal(level: Level, animal: str | None) -> str:
    """The animal that plays: the one asked for, unless the level is only for its own."""
    if animal and animal in core_animals(level):
        return animal
    return level.animal


def reskin_program(program: ir.Program, source: Pack, target: Pack) -> ir.Program:
    """The same program for another animal: its command names and item names (in place)."""
    actions = {source.action_name(n): target.action_name(n) for n in source.all_actions()}
    items = {
        source.item_name(tile): target.item_name(tile)
        for tile in source.items
        if tile in target.items
    }
    for node in ir.walk(program):
        if isinstance(node, ir.Call) and node.func in actions:
            node.func = actions[node.func]
        elif isinstance(node, ir.Name) and node.name in actions:
            node.name = actions[node.name]
        elif isinstance(node, ir.Const) and isinstance(node.value, str) and node.value in items:
            node.value = items[node.value]
    return program


def reskin_source(text: str, source: Pack, target: Pack) -> str:
    """Python text for another animal; text that doesn't parse is left as it is."""
    if not text or source.id == target.id:
        return text
    parsed = parse(text)
    if not parsed.ok or parsed.program is None:
        return text
    return print_program(reskin_program(parsed.program, source, target)).text


def reskin_text(text: str, source: Pack, target: Pack, lang: str) -> str:
    """A hint for another animal: command names in it, and the animal's and items' names."""
    if source.id == target.id:
        return text
    for neutral in source.all_actions():
        old, new = source.action_name(neutral), target.action_name(neutral)
        if old != new:
            text = re.sub(rf"\b{re.escape(old)}\(", f"{new}(", text)
    pairs: list[tuple[str, str]] = []
    src, dst = source.names.get(lang, {}), target.names.get(lang, {})
    for tile, forms in src.get("items", {}).items():
        other = dst.get("items", {}).get(tile)
        if other:
            pairs += [
                (forms[k], other.get(k, other["one"])) for k in ("many", "few", "one") if k in forms
            ]
    if src.get("animal") and dst.get("animal"):
        pairs.append((src["animal"], dst["animal"]))
    for old, new in sorted(pairs, key=lambda p: -len(p[0])):
        text = re.sub(rf"\b{re.escape(old)}\b", new, text)
    return text


def level_modules(level: Level, extra: Modules | None = None, pack: Pack | None = None) -> Modules:
    """Helper files a program may ``import``: the level's own (for this animal), then the
    learner's own."""
    own = load_pack(level.animal)
    files = {
        name: reskin_source(text, own, pack) if pack else text for name, text in level.files.items()
    }
    return {**files, **(extra or {})}


def _others_outcome(
    level: Level,
    program: ir.Program,
    pack: Pack,
    shown: int,
    max_steps: int,
    modules: Modules | None = None,
    version: tuple[int, int] | None = None,
    seed: int = 0,
) -> tuple[bool, str] | None:
    """Run the program in every world except the shown one; the first failure wins."""
    worlds = level.worlds()
    if len(worlds) == 1:
        return None
    for number, (spec, goal) in enumerate(worlds):
        if number == shown:
            continue
        world = World.from_spec(spec, pack)
        result = interpreter.run(
            program, max_steps=max_steps, modules=modules, world=world, version=version, seed=seed
        )
        world.printed = result.output
        ok, message = (False, result.error.message) if result.error else goal_met(goal, world)
        if not ok:
            return False, t(
                "It works here, but not in world {number}: {message}",
                number=number + 1,
                message=message,
            )
    return True, ""


def level_version(level: Level, python: tuple[int, int] | None = None) -> tuple[int, int]:
    """The Python release a level runs with: the learner's choice (or the newest this
    computer reads), but never older than the level needs."""
    version = python or versions.DEFAULT
    return max(version, level.min_python) if level.min_python and not python else version


def lock_reason(level: Level, python: tuple[int, int] | None = None) -> str | None:
    """Why a release island can't be played here, or ``None`` when it can."""
    need = level.min_python
    if need is None:
        return None
    if not versions.readable(need):
        return t(
            "This island needs Python {need}, but this computer runs Python {host}.",
            need=versions.version_text(need),
            host=versions.version_text(versions.HOST),
        )
    if level_version(level, python) < need:
        return t(
            "This island needs Python {need}; choose Python {need} or newer to play it.",
            need=versions.version_text(need),
        )
    return None


def run_level(
    level: Level,
    source: str,
    *,
    animal: str | None = None,
    variant: int = 0,
    max_steps: int = interpreter.MAX_STEPS,
    on_step: OnStep | None = None,
    seed: int = 0,
    modules: Modules | None = None,
    python: tuple[int, int] | None = None,
    watch: bool = False,
) -> LevelRun:
    """``watch``: every step also carries the variables' values, for the debugger."""
    worlds = level.worlds()
    variant = variant if 0 <= variant < len(worlds) else 0
    version = level_version(level, python)
    locked = lock_reason(level, python)
    if locked is not None:
        from mse_codezoo.lang_python import Diagnostic

        parsed = ParseResult(None, [Diagnostic(1, 0, locked)])
    else:
        parsed = parse(source, version)
    run = LevelRun(level, parsed, variant=variant, version=version, locked=locked)
    pack = load_pack(pick_animal(level, animal))
    run.animal = pack.id
    modules = level_modules(level, modules, pack)
    if not parsed.ok or parsed.program is None:
        run.feeling = feeling(
            animal=pack.animal_name(), parsed=False, solved=False, stars=0, error_kind="syntax"
        )
        return run
    spec, goal = worlds[variant]
    world = World.from_spec(spec, pack)
    callback = (lambda step: on_step(step, world, parsed)) if on_step else None
    result = interpreter.run(
        parsed.program,
        max_steps=max_steps,
        on_step=callback,
        modules=modules,
        world=world,
        version=version,
        seed=seed,
        watch=watch,
    )
    world.printed = result.output
    also = None
    if result.ok and goal_met(goal, world)[0]:
        also = _others_outcome(
            level, parsed.program, pack, variant, max_steps, modules, version, seed
        )
    run.world = world
    run.result = result
    run.check = check(goal, level.constraints, parsed.program, result, world, also=also)
    run.feeling = feeling(
        animal=pack.animal_name(),
        parsed=True,
        solved=run.check.solved,
        stars=run.check.earned,
        error_kind=run.error_kind,
        debugging=bool(level.starter),
        seed=seed,
    )
    return run


def solution_errors(level: Level, source: str | None = None) -> list[str]:
    """Problems with the level's reference solution; empty when it earns every star.

    ``source`` is the solution's text; by default it is read from the level's folder.
    """
    if source is None:
        if level.path is None:
            return ["level has no file path, so its reference solution can't be found"]
        path = solution_path(level.path)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            return [f"cannot read {path.name}: {exc}"]
    else:
        path = solution_path(level.path or Path("level.json"))
    if level.min_python is not None and not versions.readable(level.min_python):
        return []  # this computer's Python can't read it; see skipped_reason()
    errors: list[str] = []
    for animal in core_animals(level):
        if animal != level.animal:
            # every animal can play a core level: its re-skinned solution must work too
            other = run_level(
                level,
                reskin_source(source, load_pack(level.animal), load_pack(animal)),
                animal=animal,
            )
            if other.check is None or not other.check.solved:
                why = other.check.message if other.check else "does not parse"
                errors.append(f"{path.name} fails for the {animal}: {why}")
    for variant in range(len(level.worlds())):
        run = run_level(level, source, variant=variant)
        if not run.parsed.ok:
            return [f"{path.name}: {d.message}" for d in run.parsed.errors]
        if variant == 0:
            errors += [f"{path.name}: {d.message}" for d in run.parsed.diagnostics]
        assert run.check is not None
        if run.check.earned < len(run.check.stars):
            missing = [star.label for star in run.check.stars if not star.earned]
            where = f" in world {variant + 1}" if variant else ""
            errors.append(
                f"{path.name} earns {run.check.earned}/{len(run.check.stars)} stars{where} "
                f"({run.check.message} Missing: {'; '.join(missing)})"
            )
            break
    if level.starter:
        starter = run_level(level, level.starter)
        if starter.check is not None and starter.check.solved:
            errors.append("the starter program already solves the level; it should need fixing")
    return errors


def skipped_reason(level: Level) -> str | None:
    """Why ``solution_errors`` can't check a level on this computer, if it can't."""
    need = level.min_python
    if need is not None and not versions.readable(need):
        return (
            f"needs Python {versions.version_text(need)} "
            f"(this computer runs {versions.version_text(versions.HOST)})"
        )
    return None


# --- JSON for clients (CLI --json, web server) -----------------------------------


def run_to_json(run: LevelRun) -> dict[str, Any]:
    """Everything a client needs to replay a run: steps with lines, final world, stars."""
    data: dict[str, Any] = {
        "level": run.level.id,
        "animal": run.animal,
        "variant": run.variant,
        "diagnostics": [vars(d) for d in run.parsed.diagnostics],
        "program": ir.to_dict(run.parsed.program) if run.parsed.program else None,
        "feeling": run.feeling.to_dict() if run.feeling else None,
        "python": versions.version_text(run.version),
        "locked": run.locked,
    }
    if run.result is None or run.world is None or run.check is None:
        data["ok"] = False
        return data
    error = run.result.error
    data |= {
        "ok": run.result.ok,
        "error": (
            {
                "message": error.message,
                "kind": error.kind,
                "node_id": error.node_id,
                "line": run.line_of(error.node_id),
                "exception": type(error.exception).__name__ if error.exception else None,
                "traceback": [
                    {"function": name, "line": run.line_of(node)} for name, node in error.traceback
                ],
            }
            if error
            else None
        ),
        "output": run.result.output,
        "steps": [{**vars(step), "line": run.line_of(step.node_id)} for step in run.result.steps],
        "world": run.world.to_dict(),
        "time": run.result.time,
        "lanes": run.result.lanes,
        "files": run.result.files,
        "check": {
            "solved": run.check.solved,
            "message": run.check.message,
            "stars": [vars(star) for star in run.check.stars],
        },
    }
    return data


def world_to_json(spec: dict[str, Any], pack: Pack) -> dict[str, Any]:
    world = World.from_spec(spec, pack)
    return {**world.to_dict(), "walls": sorted([x, y] for x, y in world.walls)}


# "m03-l01" -> 3; cub and other levels have no module number
_MODULE_NUMBER = re.compile(r"^m(\d+)-")
_block_modules: dict[str, int] | None = None


def block_modules() -> dict[str, int]:
    """The module whose levels first unlock each block (palette name -> module number), for
    the gallery's "unlocks in module N". Read once from the bundled levels."""
    global _block_modules
    if _block_modules is None:
        from mse_codezoo.levels import LevelError, level_files, load_level

        found: dict[str, int] = {}
        for path in level_files():
            try:
                level = load_level(path)
            except LevelError:
                continue
            match = _MODULE_NUMBER.match(level.id)
            if not match or level.cub:
                continue
            for block in level.unlocked_blocks:
                found[block] = min(found.get(block, 99), int(match[1]))
        _block_modules = found
    return _block_modules


def level_to_json(
    level: Level, animal: str | None = None, python: tuple[int, int] | None = None
) -> dict[str, Any]:
    """A level as a client draws it: the starting worlds plus goal, limits, blocks and hints.

    Titles, hints and names come in the current language (see ``i18n.use_lang``).
    """
    from mse_codezoo.i18n import current

    own = load_pack(level.animal)
    pack = load_pack(pick_animal(level, animal))
    worlds = level.worlds()
    return {
        "id": level.id,
        "title": level.title_for(pack.id),
        "signature": level.signature,
        "minPython": versions.version_text(level.min_python) if level.min_python else None,
        "locked": lock_reason(level, python),
        "python": versions.version_text(level_version(level, python)),
        "animals": core_animals(level),
        "files": level_modules(level, pack=pack),
        "module": level.module,
        "concepts": level.concepts,
        "mode": level.mode,
        "goal": level.goal,
        "goals": [goal for _spec, goal in worlds],
        "constraints": level.constraints,
        "hints": [
            fill_items(reskin_text(h, own, pack, current()), pack)
            for h in level._text("hints", level.hints)
        ],
        "unlockedBlocks": level.unlocked_blocks,
        "starter": reskin_source(level.starter, own, pack),
        "cub": level.cub,
        "debug": level.debug,
        "blockModules": block_modules(),  # the gallery's "unlocks in module N"
        "predict": reskin_source(predict_program(level), own, pack)
        if level.cub == "predict"
        else "",
        "pack": pack.public(),
        "world": world_to_json(level.world, pack),
        "worlds": [world_to_json(spec, pack) for spec, _goal in worlds],
    }


def predict_program(level: Level) -> str:
    """The program a "predict" cub level shows: its reference solution."""
    if level.path is None:
        return ""
    try:
        return solution_path(level.path).read_text(encoding="utf-8")
    except OSError:
        return ""


def attempt_from_run(run: LevelRun, source: str) -> Attempt:
    """What a finished run adds to a learner's progress."""
    if run.check is None:  # the code could not be parsed
        return Attempt(
            run.level.id, run.level.concepts, False, 0, classify_mistakes(False, [], "syntax")
        )
    stars = [(star.earned, star.label) for star in run.check.stars]
    return Attempt(
        run.level.id,
        run.level.concepts,
        run.check.solved,
        run.check.earned,
        classify_mistakes(
            run.check.solved, stars, run.error_kind, bool(run.world and run.world.misses)
        ),
        source,
    )
