"""Goal checks and stars: the world state plus the program's structure.

Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mse_codezoo import ir
from mse_codezoo.interpreter import RunResult
from mse_codezoo.lang_python import print_program
from mse_codezoo.world import World

GOAL_TYPES = ("collect_all", "reach")
CONCEPT_NAMES = {
    "For": "a `for` loop",
    "Comment": "a comment",
    "Assign": "a variable",
    "AugAssign": "a variable update like `x += 1`",
}


@dataclass
class Star:
    earned: bool
    label: str


@dataclass
class CheckResult:
    solved: bool
    message: str
    stars: list[Star]

    @property
    def earned(self) -> int:
        return sum(star.earned for star in self.stars)


def count_lines(program: ir.Program) -> int:
    """Lines of code as printed, not counting blank lines and comments."""
    lines = print_program(program).text.splitlines()
    return sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))


def used_node_types(program: ir.Program) -> set[str]:
    return {type(node).__name__ for node in ir.walk(program)}


def goal_met(goal: dict[str, Any], world: World) -> tuple[bool, str]:
    animal = world.pack.animal
    match goal.get("type"):
        case "collect_all":
            item = goal["item"]
            noun = world.pack.item_name(item)
            left = world.remaining(item)
            if left == 0:
                return True, f"The {animal} collected every {noun}!"
            return False, f"{left} {noun}{'s' if left > 1 else ''} still to collect."
        case "reach":
            if [world.x, world.y] == list(goal["at"]):
                return True, f"The {animal} got there!"
            return False, f"The {animal} hasn't reached the goal yet."
    raise ValueError(f"unknown goal type {goal.get('type')!r}")


def check(
    goal: dict[str, Any],
    constraints: dict[str, Any],
    program: ir.Program,
    result: RunResult,
    world: World,
) -> CheckResult:
    if result.error is not None:
        solved, message = False, result.error.message
    else:
        solved, message = goal_met(goal, world)

    stars = [Star(solved, "Solved the level")]

    max_lines = constraints.get("maxLines")
    if max_lines is None:
        stars.append(Star(solved, "No line limit"))
    else:
        used = count_lines(program)
        stars.append(
            Star(solved and used <= max_lines, f"{max_lines} lines or fewer (used {used})")
        )

    must_use = list(constraints.get("mustUse", []))
    if must_use:
        names = ", ".join(CONCEPT_NAMES.get(n, f"`{n}`") for n in must_use)
        present = used_node_types(program)
        stars.append(Star(solved and all(n in present for n in must_use), f"Used {names}"))
    else:
        stars.append(Star(solved, "No concept required"))

    return CheckResult(solved, message, stars)
