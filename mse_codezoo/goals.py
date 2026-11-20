"""Goal checks and stars: the world state plus the program's structure.

Goal types:

* ``collect_all`` ``{"item": "B", "avoid": "R"?}``: pick up every ``B``; with ``avoid``,
  picking up any ``R`` fails the level.
* ``reach`` ``{"at": [x, y]}``: end on that square.
* ``say`` ``{"text": "3 bananas"}``: the animal says exactly this at some point;
  or ``{"texts": ["yum", "hmm"]}``: it says exactly these, in this order, and nothing else.
* ``avoid`` ``{"item": "R"}``: never pick up an ``R``.
* ``build`` ``{"logs": {"oak": 2, "pine": 1}}``: the beaver built exactly these logs into
  the dam.
* ``all`` ``{"goals": [...]}``: every goal in the list.

Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mse_codezoo import ir
from mse_codezoo.i18n import t
from mse_codezoo.interpreter import RunResult
from mse_codezoo.lang_python import print_program
from mse_codezoo.world import World

GOAL_TYPES = ("collect_all", "reach", "say", "avoid", "build", "all")


def concept_name(node_type: str) -> str:
    """How a ``mustUse`` node type reads in a star label."""
    names = {
        "For": t("a `for` loop"),
        "While": t("a `while` loop"),
        "If": t("an `if`"),
        "Compare": t("a comparison like `<` or `==`"),
        "BoolOp": t("`and` / `or`"),
        "FString": t("an f-string"),
        "MethodCall": t("a text command like `.upper()`"),
        "Subscript": t("`[ ]` to pick letters"),
        "Comment": t("a comment"),
        "Assign": t("a variable"),
        "AugAssign": t("a variable update like `x += 1`"),
        "UnaryOp": t("`not` or a minus sign"),
        "BinOp": t("an operator like `+` or `*`"),
        "Break": t("`break`"),
        "Continue": t("`continue`"),
        "FunctionDef": t("a function (`def`)"),
        "Return": t("`return`"),
        "Try": t("`try` / `except`"),
        "Raise": t("`raise`"),
        "Assert": t("`assert`"),
        "Import": t("`import`"),
        "List": t("a list"),
        "Tuple": t("a tuple"),
        "Dict": t("a dictionary"),
        "Set": t("a set"),
        "Comprehension": t("a comprehension"),
        "Recursion": t("a function that calls itself"),
        "Global": t("`global`"),
    }
    return names.get(node_type, f"`{node_type}`")


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
    """Node type names in the program, plus ``Recursion`` for a function that calls itself."""
    found = {type(node).__name__ for node in ir.walk(program)}
    for node in ir.walk(program):
        if isinstance(node, ir.FunctionDef) and any(
            isinstance(inner, ir.Call) and inner.func == node.name
            for stmt in node.body
            for inner in ir.walk(stmt)
        ):
            found.add("Recursion")
    return found


PSEUDO_CONCEPTS = ("Recursion",)  # allowed in ``mustUse`` besides node type names


def goal_met(goal: dict[str, Any], world: World) -> tuple[bool, str]:
    pack = world.pack
    animal = pack.animal_name()
    match goal.get("type"):
        case "collect_all":
            item = goal["item"]
            avoid = goal.get("avoid")
            if avoid and world.collected.get(avoid):
                return False, t(
                    "Oh no, the {animal} picked up a {bad}! Leave those where they are.",
                    animal=animal,
                    bad=pack.noun(avoid),
                )
            left = world.remaining(item)
            if left == 0:
                return True, t(
                    "The {animal} collected every {noun}!",
                    animal=animal,
                    noun=pack.noun(item),
                    nouns=pack.nouns(item),
                )
            return False, t(
                "{count} {noun} still to collect.", count=left, noun=pack.noun(item, left)
            )
        case "reach":
            if [world.x, world.y] == list(goal["at"]):
                return True, t("The {animal} got there!", animal=animal)
            return False, t("The {animal} hasn't reached the goal yet.", animal=animal)
        case "avoid":
            bad = goal["item"]
            if world.collected.get(bad):
                return False, t(
                    "Oh no, the {animal} picked up a {bad}! Leave those where they are.",
                    animal=animal,
                    bad=pack.noun(bad),
                )
            return True, t(
                "The {animal} left every {bad} alone.", animal=animal, bad=pack.noun(bad)
            )
        case "say" if "texts" in goal:
            wanted = [str(text) for text in goal["texts"]]
            if world.said == wanted:
                return True, t('The {animal} said "{text}"!', animal=animal, text=", ".join(wanted))
            return False, t(
                'The {animal} said "{said}", but should say "{text}".',
                animal=animal,
                said=", ".join(world.said),
                text=", ".join(wanted),
            )
        case "say":
            text = str(goal["text"])
            if text in world.said:
                return True, t('The {animal} said "{text}"!', animal=animal, text=text)
            if world.said:
                return False, t(
                    'The {animal} said "{said}", but should say "{text}".',
                    animal=animal,
                    said=world.said[-1],
                    text=text,
                )
            return False, t('The {animal} should say "{text}".', animal=animal, text=text)
        case "build":
            wanted = {str(k): int(v) for k, v in goal["logs"].items()}
            if world.built == wanted:
                return True, t("The {animal} built the dam!", animal=animal)
            missing = ", ".join(
                f"{name} {wanted[name] - world.built.get(name, 0)}"
                for name in sorted(wanted)
                if world.built.get(name, 0) < wanted[name]
            )
            if missing:
                return False, t("The dam still needs: {logs}.", logs=missing)
            return False, t("The dam has the wrong logs in it: {logs}.", logs=world.built)
        case "all":
            messages = []
            for part in goal["goals"]:
                ok, message = goal_met(part, world)
                if not ok:
                    return False, message
                messages.append(message)
            return True, messages[0]  # the first goal is the main one
    raise ValueError(f"unknown goal type {goal.get('type')!r}")


def goal_errors(goal: Any, world: World | None) -> list[str]:
    """Problems with a goal object, for ``codezoo levels validate``."""
    if not isinstance(goal, dict) or goal.get("type") not in GOAL_TYPES:
        return [f"goal.type must be one of {', '.join(GOAL_TYPES)}"]
    match goal["type"]:
        case "collect_all":
            if world is not None and world.remaining(goal.get("item")) == 0:
                return [f"goal item {goal.get('item')!r} does not appear in the world"]
        case "reach":
            if not (isinstance(goal.get("at"), list) and len(goal["at"]) == 2):
                return ["goal.at must be [x, y]"]
        case "say":
            texts = goal.get("texts")
            if texts is not None:
                if not isinstance(texts, list) or not all(isinstance(x, str) for x in texts):
                    return ["goal.texts must be a list of texts"]
            elif not isinstance(goal.get("text"), str) or not goal["text"]:
                return ["goal.text must be the text to say"]
        case "avoid":
            if not isinstance(goal.get("item"), str):
                return ["goal.item must be a tile letter"]
        case "build":
            logs = goal.get("logs")
            if not isinstance(logs, dict) or not all(
                isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in logs.items()
            ):
                return ['goal.logs must be like {"oak": 2}']
        case "all":
            parts = goal.get("goals")
            if not isinstance(parts, list) or not parts:
                return ["goal.goals must be a list of goals"]
            return [error for part in parts for error in goal_errors(part, world)]
    return []


def check(
    goal: dict[str, Any],
    constraints: dict[str, Any],
    program: ir.Program,
    result: RunResult,
    world: World,
    *,
    also: tuple[bool, str] | None = None,
) -> CheckResult:
    """Stars for one run. ``also`` is the outcome in the level's other worlds, if any."""
    if result.error is not None:
        solved, message = False, result.error.message
    else:
        solved, message = goal_met(goal, world)
        if solved and also is not None and not also[0]:
            solved, message = also

    stars = [Star(solved, t("Solved the level"))]

    max_lines = constraints.get("maxLines")
    if max_lines is None:
        stars.append(Star(solved, t("No line limit")))
    else:
        used = count_lines(program)
        stars.append(
            Star(
                solved and used <= max_lines,
                t("{max} lines or fewer (used {used})", max=max_lines, used=used),
            )
        )

    must_use = list(constraints.get("mustUse", []))
    if must_use:
        names = ", ".join(concept_name(n) for n in must_use)
        present = used_node_types(program)
        stars.append(
            Star(solved and all(n in present for n in must_use), t("Used {names}", names=names))
        )
    else:
        stars.append(Star(solved, t("No concept required")))

    return CheckResult(solved, message, stars)
