"""Terminal stage for ``codezoo play``: a coloured character grid that replays a run.

The replay works from the run's events (``move``, ``turn``, ``grab``, ``say``, ``bump``
and the tricks' ``swing``, ``climb``, ``build``, ``crack``, ``hide``), exactly like the web
stage, so both show the same thing. ``codezoo replay`` uses it for saved runs and the
storybook uses ``StageState`` to draw its pictures. Standard library only.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from mse_codezoo.i18n import t
from mse_codezoo.world import ARROWS, Pack

RESET = "\x1b[0m"
CLEAR = "\x1b[2J\x1b[H"
STYLES = {
    "animal": "\x1b[1;33m",
    "wall": "\x1b[90m",
    "empty": "\x1b[2m",
    "B": "\x1b[93m",
    "C": "\x1b[33m",
    "R": "\x1b[32m",
    "item": "\x1b[96m",
    "bump": "\x1b[1;31m",
    "~": "\x1b[34m",
    "t": "\x1b[32m",
    "-": "\x1b[37m",
    "o": "\x1b[31m",
    "=": "\x1b[33m",
    "say": "\x1b[1;35m",
    "line": "\x1b[1;36m",
}
SPEEDS = {1: 0.6, 2: 0.35, 3: 0.2, 4: 0.1, 5: 0.03}


@dataclass
class StageState:
    """What the terminal stage shows: built from a level's world, changed by events."""

    width: int
    height: int
    walls: set[tuple[int, int]]
    items: dict[tuple[int, int], str]
    position: tuple[int, int]
    facing: str
    bubble: str | None = None
    bumped: bool = False
    said: list[str] = field(default_factory=list)
    terrain: dict[tuple[int, int], str] = field(default_factory=dict)
    collected: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, world: dict[str, Any]) -> StageState:
        width, height = world["size"]
        return cls(
            width,
            height,
            {(x, y) for x, y in world["walls"]},
            {(x, y): tile for x, y, tile in world["items"]},
            (world["position"][0], world["position"][1]),
            world["facing"],
            terrain={(x, y): kind for x, y, kind in world.get("terrain", [])},
        )

    def apply(self, event: dict[str, Any]) -> None:
        self.bubble = None
        self.bumped = False
        match event["type"]:
            case "move" | "swing":
                self.position = (event["to"][0], event["to"][1])
            case "turn":
                self.facing = event["facing"]
            case "grab" | "climb":
                if event.get("item"):
                    self.items.pop((event["at"][0], event["at"][1]), None)
                    self.collected.append(event["item"])
                else:
                    self.bubble = "?"
            case "build":
                self.terrain[(event["at"][0], event["at"][1])] = "="
            case "crack":
                self.bumped = True
            case "say":
                self.bubble = event["text"]
                self.said.append(event["text"])
            case "bump":
                self.bumped = True


# events with nothing to draw on the grid (print() shows in the terminal itself)
UNSEEN = ("sense", "call", "return", "print")


def paint(text: str, style: str, color: bool) -> str:
    return f"{STYLES[style]}{text}{RESET}" if color else text


def render(state: StageState, *, color: bool = True) -> str:
    """The grid with a frame, the animal as an arrow, and a speech bubble above."""
    lines = []
    if state.bubble:
        lines.append("  " + paint(f'"{state.bubble}"', "say", color))
    border = "+" + "-" * (state.width * 2 + 1) + "+"
    lines.append(border)
    for y in range(state.height):
        cells = []
        for x in range(state.width):
            if (x, y) == state.position:
                style = "bump" if state.bumped else "animal"
                cells.append(paint("*" if state.bumped else ARROWS[state.facing], style, color))
            elif (x, y) in state.walls:
                cells.append(paint("#", "wall", color))
            elif (x, y) in state.items:
                tile = state.items[(x, y)]
                cells.append(paint(tile, tile if tile in STYLES else "item", color))
            elif (x, y) in state.terrain:
                kind = state.terrain[(x, y)]
                cells.append(paint(kind, kind, color))
            else:
                cells.append(paint(".", "empty", color))
        lines.append("| " + " ".join(cells) + " |")
    lines.append(border)
    return "\n".join(lines)


def terrain_name(kind: str) -> str:
    names = {
        "~": t("water"),
        "t": t("tree"),
        "-": t("thin ice"),
        "o": t("guard"),
        "=": t("bridge"),
    }
    return names.get(kind, kind)


def legend(pack: Pack, items: Iterable[str], terrain: Iterable[str] = ()) -> str:
    """``> monkey   # rock   B banana`` for the tiles that appear in a level."""
    parts = [f"> {pack.animal_name()}", "# rock"]
    parts += [f"{tile} {pack.noun(tile)}" for tile in sorted(set(items))]
    parts += [f"{kind} {terrain_name(kind)}" for kind in sorted(set(terrain))]
    return "   ".join(parts)


def replay(
    world: dict[str, Any],
    steps: list[dict[str, Any]],
    source_lines: list[str],
    *,
    echo: Callable[[str], None],
    color: bool = True,
    animate: bool = True,
    speed: int = 3,
    header: str = "",
) -> StageState:
    """Show a run step by step. Without ``animate``, only the final grid is shown."""
    state = StageState.from_json(world)
    delay = SPEEDS.get(speed, SPEEDS[3])

    def frame(line: int | None) -> None:
        code = ""
        if line and 0 < line <= len(source_lines):
            code = paint(f"{line:>3} | {source_lines[line - 1].rstrip()}", "line", color)
        echo(CLEAR + header + "\n" + render(state, color=color) + "\n" + code)

    for step in steps:
        events = [e for e in step.get("events", []) if e["type"] not in UNSEEN]
        if not events and animate:
            frame(step.get("line"))
            time.sleep(delay / 2)
        for event in events:
            state.apply(event)
            if animate:
                frame(step.get("line"))
                time.sleep(delay * (3 if event["type"] in ("say", "bump", "crack") else 1))
    if not animate:
        echo(render(state, color=color))
    return state
