"""Play one level: parse the learner's code, run it in the world, check the goal.

A level may have several worlds (``variants``): the program runs in the one being shown,
then quietly in all the others, and the level is solved only when it works everywhere.
That is what makes ``if`` worth learning. Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mse_codezoo import interpreter, ir
from mse_codezoo.feelings import Feeling, feeling
from mse_codezoo.goals import CheckResult, check, goal_met
from mse_codezoo.i18n import t
from mse_codezoo.interpreter import RunResult, Step
from mse_codezoo.lang_python import ParseResult, parse
from mse_codezoo.levels import Level, load_pack, solution_path
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


def _others_outcome(
    level: Level, program: ir.Program, pack: Pack, shown: int, max_steps: int
) -> tuple[bool, str] | None:
    """Run the program in every world except the shown one; the first failure wins."""
    worlds = level.worlds()
    if len(worlds) == 1:
        return None
    for number, (spec, goal) in enumerate(worlds):
        if number == shown:
            continue
        world = World.from_spec(spec, pack)
        result = interpreter.run(program, world.actions(), world.drain_events, max_steps)
        ok, message = (False, result.error.message) if result.error else goal_met(goal, world)
        if not ok:
            return False, t(
                "It works here, but not in world {number}: {message}",
                number=number + 1,
                message=message,
            )
    return True, ""


def run_level(
    level: Level,
    source: str,
    *,
    animal: str | None = None,
    variant: int = 0,
    max_steps: int = interpreter.MAX_STEPS,
    on_step: OnStep | None = None,
    seed: int = 0,
) -> LevelRun:
    worlds = level.worlds()
    variant = variant if 0 <= variant < len(worlds) else 0
    parsed = parse(source)
    run = LevelRun(level, parsed, variant=variant)
    pack = load_pack(animal or level.animal)
    if not parsed.ok or parsed.program is None:
        run.feeling = feeling(
            animal=pack.animal_name(), parsed=False, solved=False, stars=0, error_kind="syntax"
        )
        return run
    spec, goal = worlds[variant]
    world = World.from_spec(spec, pack)
    callback = (lambda step: on_step(step, world, parsed)) if on_step else None
    result = interpreter.run(
        parsed.program, world.actions(), world.drain_events, max_steps, on_step=callback
    )
    also = None
    if result.ok and goal_met(goal, world)[0]:
        also = _others_outcome(level, parsed.program, pack, variant, max_steps)
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


def solution_errors(level: Level) -> list[str]:
    """Problems with the level's reference solution; empty when it earns every star."""
    if level.path is None:
        return ["level has no file path, so its reference solution can't be found"]
    path = solution_path(level.path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read {path.name}: {exc}"]
    errors: list[str] = []
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


# --- JSON for clients (CLI --json, web server) -----------------------------------


def run_to_json(run: LevelRun) -> dict[str, Any]:
    """Everything a client needs to replay a run: steps with lines, final world, stars."""
    data: dict[str, Any] = {
        "level": run.level.id,
        "variant": run.variant,
        "diagnostics": [vars(d) for d in run.parsed.diagnostics],
        "program": ir.to_dict(run.parsed.program) if run.parsed.program else None,
        "feeling": run.feeling.to_dict() if run.feeling else None,
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
            }
            if error
            else None
        ),
        "output": run.result.output,
        "steps": [{**vars(step), "line": run.line_of(step.node_id)} for step in run.result.steps],
        "world": run.world.to_dict(),
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


def level_to_json(level: Level, animal: str | None = None) -> dict[str, Any]:
    """A level as a client draws it: the starting worlds plus goal, limits, blocks and hints.

    Titles, hints and names come in the current language (see ``i18n.use_lang``).
    """
    pack = load_pack(animal or level.animal)
    worlds = level.worlds()
    return {
        "id": level.id,
        "title": level.shown_title,
        "module": level.module,
        "concepts": level.concepts,
        "mode": level.mode,
        "goal": level.goal,
        "goals": [goal for _spec, goal in worlds],
        "constraints": level.constraints,
        "hints": level.shown_hints,
        "unlockedBlocks": level.unlocked_blocks,
        "starter": level.starter,
        "pack": pack.public(),
        "world": world_to_json(level.world, pack),
        "worlds": [world_to_json(spec, pack) for spec, _goal in worlds],
    }


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
        classify_mistakes(run.check.solved, stars, run.error_kind),
        source,
    )
