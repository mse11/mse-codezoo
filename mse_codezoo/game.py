"""Play one level: parse the learner's code, run it in the world, check the goal.

Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mse_codezoo import interpreter, ir
from mse_codezoo.goals import CheckResult, check
from mse_codezoo.interpreter import RunResult, Step
from mse_codezoo.lang_python import ParseResult, parse
from mse_codezoo.levels import Level, load_pack, solution_path
from mse_codezoo.profiles import Attempt, classify_mistakes
from mse_codezoo.world import NEUTRAL_ACTIONS, World

OnStep = Callable[[Step, World, ParseResult], None]


@dataclass
class LevelRun:
    level: Level
    parsed: ParseResult
    world: World | None = None
    result: RunResult | None = None
    check: CheckResult | None = None

    def line_of(self, node_id: str | None) -> int | None:
        span = self.parsed.positions.get(node_id or "")
        return span.line if span else None


def run_level(
    level: Level,
    source: str,
    *,
    animal: str | None = None,
    max_steps: int = interpreter.MAX_STEPS,
    on_step: OnStep | None = None,
) -> LevelRun:
    parsed = parse(source)
    run = LevelRun(level, parsed)
    if not parsed.ok or parsed.program is None:
        return run
    world = World.from_spec(level.world, load_pack(animal or level.animal))
    callback = (lambda step: on_step(step, world, parsed)) if on_step else None
    result = interpreter.run(
        parsed.program, world.actions(), world.drain_events, max_steps, on_step=callback
    )
    run.world = world
    run.result = result
    run.check = check(level.goal, level.constraints, parsed.program, result, world)
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
    run = run_level(level, source)
    if not run.parsed.ok:
        return [f"{path.name}: {d.message}" for d in run.parsed.errors]
    errors = [f"{path.name}: {d.message}" for d in run.parsed.diagnostics]
    assert run.check is not None
    if run.check.earned < len(run.check.stars):
        missing = [star.label for star in run.check.stars if not star.earned]
        errors.append(
            f"{path.name} earns {run.check.earned}/{len(run.check.stars)} stars "
            f"({run.check.message} Missing: {'; '.join(missing)})"
        )
    return errors


# --- JSON for clients (CLI --json, web server) -----------------------------------


def run_to_json(run: LevelRun) -> dict[str, Any]:
    """Everything a client needs to replay a run: steps with lines, final world, stars."""
    data: dict[str, Any] = {
        "level": run.level.id,
        "diagnostics": [vars(d) for d in run.parsed.diagnostics],
        "program": ir.to_dict(run.parsed.program) if run.parsed.program else None,
    }
    if run.result is None or run.world is None or run.check is None:
        data["ok"] = False
        return data
    error = run.result.error
    data |= {
        "ok": run.result.ok,
        "error": (
            {"message": error.message, "node_id": error.node_id, "line": run.line_of(error.node_id)}
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


def level_to_json(level: Level, animal: str | None = None) -> dict[str, Any]:
    """A level as a client draws it: the starting world plus goal, limits, blocks and hints."""
    pack = load_pack(animal or level.animal)
    world = World.from_spec(level.world, pack)
    return {
        "id": level.id,
        "title": level.title,
        "module": level.module,
        "concepts": level.concepts,
        "mode": level.mode,
        "goal": level.goal,
        "constraints": level.constraints,
        "hints": level.hints,
        "unlockedBlocks": level.unlocked_blocks,
        "starter": level.starter,
        "pack": {
            "id": pack.id,
            "animal": pack.animal,
            "world": pack.world,
            "actions": {name: pack.action_name(name) for name in NEUTRAL_ACTIONS},
            "items": pack.items,
        },
        "world": {
            **world.to_dict(),
            "walls": sorted([x, y] for x, y in world.walls),
        },
    }


def attempt_from_run(run: LevelRun, source: str) -> Attempt:
    """What a finished run adds to a learner's progress."""
    if run.check is None:  # the code could not be parsed
        message = run.parsed.errors[0].message if run.parsed.errors else None
        return Attempt(
            run.level.id, run.level.concepts, False, 0, classify_mistakes(False, [], message)
        )
    stars = [(star.earned, star.label) for star in run.check.stars]
    error = run.result.error.message if run.result and run.result.error else None
    return Attempt(
        run.level.id,
        run.level.concepts,
        run.check.solved,
        run.check.earned,
        classify_mistakes(run.check.solved, stars, error),
        source,
    )
