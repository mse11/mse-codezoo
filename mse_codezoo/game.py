"""Play one level: parse the learner's code, run it in the world, check the goal.

Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mse_codezoo import interpreter
from mse_codezoo.goals import CheckResult, check
from mse_codezoo.interpreter import RunResult, Step
from mse_codezoo.lang_python import ParseResult, parse
from mse_codezoo.levels import Level, load_pack, solution_path
from mse_codezoo.world import World

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
