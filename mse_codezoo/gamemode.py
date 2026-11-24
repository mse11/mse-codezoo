"""Game mode: a program writes the rules of a world, then someone plays it live.

A level's program runs once and is done. A game's program runs once to *set up* (it
teaches functions and classes, makes critters), and then the game calls its event
handlers on every tick of the clock:

- ``on_key(key)`` for each key the player pressed (``"up"``, ``"down"``, ``"left"``,
  ``"right"``, ``"space"``); without one, the arrows move the animal;
- ``on_tick()`` once per tick, and ``on_tick(self)`` on every critter whose class has one;
- ``on_item(item)`` when the animal arrives on an item (``"banana"``);
- ``on_touch(critter)`` when a critter and the animal meet.

Critters are the program's own classes built on ``Critter``. Their place is kept by the
game, not on the object, so a program reads ``self.x`` but moves only with ``step()``.
Programs also get ``score``, ``win()``, ``lose()``, ``go(direction)``, ``where()``,
``ticks()`` and ``critters()``.

Everything stays on the grid and the clock counts whole ticks, so a game is
deterministic: the same program, seed and keys give the same game, in CPython and in
Pyodide. Each tick has a budget of interpreter steps, so an endless loop in a handler
ends the game with a kind message instead of freezing it.

Bumps never crash a game: the animal or the critter just stays where it is.

Games live as JSON files in ``content/games``; a running game is a ``Game``, and
``Sessions`` keeps the running games of ``codezoo serve`` (and of the offline build's
web worker) between ticks. Standard library only.

G1 adds what a child needs to make a game alone: every bundled game is a *template*
(collect, dodge, chase, maze) with *lesson rounds* (``rounds``: one visible change per
round, checked against ``Game.features()``), *twist cards* for the last round, and the
"Test my game" playtest bot (``playtest()``): bot animals play the game a few dozen times
on the simulated clock and say in kind words whether it can be won.

G2 adds *objects with attached scripts*: a world's ``objects`` name a class of the
program (``{"at": [3, 1], "class": "Guard"}``), and the game makes one of them on that
square after the setup, by calling ``Guard(3, 1)``. Programs can also *build with code*
(``build.block(x, y, "stone")``, ``build.clear(x, y)``, ``build.item(x, y)``).

Worlds can also hold *doors*, *switches* and *power-ups* as objects of their own
(``{"at": [4, 1], "type": "door"}``): a closed door blocks like a stone, stepping on a
switch opens or closes its doors and calls ``on_switch(name)``, and a power-up calls
``on_power()`` (without one, the critters freeze for a while). Programs open doors with
``door("door").open()`` and play sounds with ``sound("ding")``.

Every tick says which handlers ran and what each one changed (``fired``), for the game
page's "Which handler fired?" view.

G3 (several animals in one world) lives in ``gamerooms.py``; the hooks it needs are here:
``player()``, ``animals()`` and the per-animal parts of a tick.
"""

from __future__ import annotations

import io
import json
import random
import re
import secrets
import threading
import time
import tokenize
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mse_codezoo import interpreter, versions
from mse_codezoo.i18n import current, t
from mse_codezoo.interpreter import LearnerError, Runner, ZooObject
from mse_codezoo.lang_python import ParseResult, parse
from mse_codezoo.levels import animal_names, load_pack
from mse_codezoo.world import (
    BRIDGE,
    CLOCKWISE,
    DIRECTIONS,
    NEUTRAL_ACTIONS,
    THIN_ICE,
    TREE,
    WALL,
    WATER,
    World,
)

GAMES_DIR = Path(__file__).parent / "content" / "games"

TICK_BUDGET = 1_000  # interpreter steps per tick, for every handler together
SETUP_STEPS = interpreter.MAX_STEPS
MAX_TICKS = 3_000  # about 6 minutes at the usual speed
MAX_CRITTERS = 30
MAX_KEYS = 4  # keys handled per tick; more are dropped
MAX_LINES = 40  # lines lit up per tick
MAX_OUTPUT = 200  # printed lines kept per game
KEYS = ("up", "down", "left", "right", "space")
KEY_DIRECTION = {"up": "north", "right": "east", "down": "south", "left": "west"}
TICK_MS = 150  # how long a tick lasts on screen; the engine itself has no wall clock
HANDLERS = ("on_key", "on_tick", "on_item", "on_touch", "on_switch", "on_power")
WIN_RULES = ("collect_all", "score", "survive")
PLAYING, WON, LOST, OVER, BROKEN = "playing", "won", "lost", "over", "error"
TEMPLATES = ("collect", "dodge", "chase", "maze")
MAX_ROUNDS = 8
MAX_OBJECTS = MAX_CRITTERS
MAX_BUILDS = 2_000  # squares a game may change with `build`
CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,30}")
# what `build.block(x, y, kind)` can put on a square
BLOCKS = {"stone": WALL, "wall": WALL, "water": WATER, "tree": TREE, "ice": THIN_ICE}
BLOCKS |= {"bridge": BRIDGE}
# what a round can ask for (anything else is a name that must appear in the code)
FEATURES = ("on_key", "on_tick", "on_item", "on_touch", "critter", "critters2", "critter_tick")
FEATURES += ("object", "build")
OBJECT_TYPES = ("door", "switch", "power")
FREEZE_TICKS = 20  # a power-up without on_power() freezes the critters this long
SOUNDS = ("ding", "boing", "pop", "drum", "whoosh", "tada", "oops", "click")
MAX_SOUNDS = 4  # sounds a game may play in one tick; more are left out
BOT_GAMES = 30  # the playtest bot in the browser: enough to say "nobody could win"
MAX_BOT_GAMES = 100
BOT_TICKS = 200


class GameError(ValueError):
    """A game file that can't be played: unknown id, bad rules, bad world."""


# --- game files -------------------------------------------------------------------------


@dataclass
class GameSpec:
    """A game as its JSON file describes it.

    ``rules`` are the game's own rules, checked after every tick: ``win`` is
    ``"collect_all"`` (every item collected), ``{"score": N}`` or ``{"survive": N}``
    (still playing after N ticks); ``caught`` makes a critter touching the animal lose the
    game when the program has no ``on_touch``. A program can always call ``win()`` and
    ``lose()`` itself.
    """

    id: str
    title: dict[str, str]
    world: dict[str, Any]
    animal: str = "monkey"
    template: str = ""
    rules: dict[str, Any] = field(default_factory=dict)
    starter: str = ""
    help: dict[str, list[str]] = field(default_factory=dict)
    max_ticks: int = MAX_TICKS
    rounds: list[dict[str, Any]] = field(default_factory=list)
    lesson: str = ""  # the small program the lesson rounds start from

    @classmethod
    def from_dict(cls, data: Any) -> GameSpec:
        if not isinstance(data, dict):
            raise GameError("a game must be a JSON object")
        game_id = data.get("id")
        if not isinstance(game_id, str) or not game_id:
            raise GameError("a game needs an id")
        title = data.get("title", {})
        if isinstance(title, str):
            title = {"en": title}
        if not isinstance(title, dict) or not all(isinstance(v, str) for v in title.values()):
            raise GameError("title must be text, or text per language")
        world = data.get("world")
        if not isinstance(world, dict):
            raise GameError("a game needs a world")
        animal = data.get("animal", "monkey")
        if animal not in animal_names():
            raise GameError(f"no animal called {animal!r}")
        rules = data.get("rules", {})
        if not isinstance(rules, dict):
            raise GameError("rules must be an object")
        win = rules.get("win")
        if win is not None and not (
            win == "collect_all"
            or (
                isinstance(win, dict)
                and len(win) == 1
                and next(iter(win)) in ("score", "survive")
                and isinstance(next(iter(win.values())), int)
                and next(iter(win.values())) > 0
            )
        ):
            raise GameError('rules.win must be "collect_all", {"score": N} or {"survive": N}')
        max_ticks = data.get("max_ticks", MAX_TICKS)
        if not isinstance(max_ticks, int) or not 1 <= max_ticks <= MAX_TICKS:
            raise GameError(f"max_ticks must be a whole number from 1 to {MAX_TICKS}")
        help_ = data.get("help", {})
        if not isinstance(help_, dict) or not all(isinstance(v, list) for v in help_.values()):
            raise GameError("help must map a language to a list of lines")
        template = str(data.get("template", ""))
        if template and template not in TEMPLATES:
            raise GameError(f"template must be one of {', '.join(TEMPLATES)}")
        starter = data.get("starter", "")
        if not isinstance(starter, str) or len(starter) > 20_000:
            raise GameError("starter must be text")
        rounds = _rounds(data.get("rounds", []))
        lesson = data.get("lesson", "")
        if not isinstance(lesson, str) or len(lesson) > 20_000:
            raise GameError("lesson must be text")
        spec = cls(
            id=game_id,
            title=dict(title),
            world=world,
            animal=animal,
            template=template,
            rules=dict(rules),
            starter=starter,
            help={k: [str(line) for line in v] for k, v in help_.items()},
            max_ticks=max_ticks,
            rounds=rounds,
            lesson=lesson,
        )
        built = World.from_spec(world, load_pack(animal))  # raises ValueError on a bad world
        _objects(world.get("objects", []), built)
        return spec

    def title_text(self) -> str:
        return self.title.get(current()) or self.title.get("en") or self.id

    def help_lines(self) -> list[str]:
        return self.help.get(current()) or self.help.get("en") or []

    def objects(self) -> list[dict[str, Any]]:
        return list(self.world.get("objects", []))

    def to_dict(self) -> dict[str, Any]:
        """The game as its file says it: what share links and class shares carry."""
        data: dict[str, Any] = {
            "id": self.id,
            "title": dict(self.title),
            "template": self.template,
            "animal": self.animal,
            "world": self.world,
            "rules": dict(self.rules),
            "max_ticks": self.max_ticks,
            "help": {k: list(v) for k, v in self.help.items()},
            "starter": self.starter,
        }
        if self.rounds:
            data["rounds"] = [dict(r) for r in self.rounds]
        if self.lesson:
            data["lesson"] = self.lesson
        return data

    def rounds_text(self) -> list[dict[str, Any]]:
        """The lesson rounds in the current language."""
        return [
            {
                "title": _in_lang(r["title"]),
                "goal": _in_lang(r["goal"]),
                "needs": list(r.get("needs", [])),
                "twist": bool(r.get("twist")),
                "hint": _in_lang(r.get("hint", {})),
            }
            for r in self.rounds
        ]


def _in_lang(text: dict[str, str]) -> str:
    return text.get(current()) or text.get("en") or ""


def _texts(value: Any, what: str) -> dict[str, str]:
    if isinstance(value, str):
        value = {"en": value}
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise GameError(f"{what} must be text, or text per language")
    return dict(value)


def _rounds(data: Any) -> list[dict[str, Any]]:
    """Lesson rounds: one visible change each, like "make the guard walk"."""
    if not isinstance(data, list) or len(data) > MAX_ROUNDS:
        raise GameError(f"rounds must be a list of at most {MAX_ROUNDS}")
    rounds = []
    for number, entry in enumerate(data, 1):
        if not isinstance(entry, dict):
            raise GameError(f"round {number} must be an object")
        needs = entry.get("needs", [])
        if not isinstance(needs, list) or not all(
            isinstance(n, str) and CLASS_NAME.fullmatch(n) for n in needs
        ):
            raise GameError(f"round {number}: needs must be a list of names")
        found = {
            "title": _texts(entry.get("title"), f"round {number}'s title"),
            "goal": _texts(entry.get("goal"), f"round {number}'s goal"),
            "needs": list(needs),
        }
        if "hint" in entry:
            found["hint"] = _texts(entry["hint"], f"round {number}'s hint")
        if entry.get("twist"):
            found["twist"] = True
        rounds.append(found)
    return rounds


def _objects(data: Any, world: World) -> None:
    """A world's objects: squares where the game makes one of the program's critters."""
    if not isinstance(data, list) or len(data) > MAX_OBJECTS:
        raise GameError(f"world.objects must be a list of at most {MAX_OBJECTS}")
    taken = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise GameError('world.objects entries must be {"at": [x, y], "class": "Guard"}')
        at = entry.get("at")
        if not (
            isinstance(at, list)
            and len(at) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in at)
        ):
            raise GameError("an object needs a square: [x, y]")
        x, y = at
        if not world._inside(x, y) or (x, y) in world.walls:
            raise GameError(f"the object at ({x}, {y}) is outside the grid or on a rock")
        if world.terrain.get((x, y)) in (WATER, TREE) or (x, y) == (world.x, world.y):
            raise GameError(f"the object at ({x}, {y}) needs an open square")
        if (x, y) in taken:
            raise GameError(f"two objects at ({x}, {y})")
        taken.add((x, y))
        kind_of = entry.get("type")
        if kind_of is not None:
            if kind_of not in OBJECT_TYPES:
                raise GameError(f"the object at ({x}, {y}) has an unknown type {kind_of!r}")
            for key in ("name", "door"):
                value = entry.get(key, "door")
                if not isinstance(value, str) or not CLASS_NAME.fullmatch(value):
                    raise GameError(f"the object at ({x}, {y}) needs a plain name for its {key}")
            if not isinstance(entry.get("open", False), bool):
                raise GameError(f"the door at ({x}, {y}): open must be true or false")
            continue
        name = entry.get("class", "")
        if not isinstance(name, str) or not CLASS_NAME.fullmatch(name):
            raise GameError(f'the object at ({x}, {y}) needs a class name, like "Guard"')
        if entry.get("facing", "east") not in DIRECTIONS:
            raise GameError(f"the object at ({x}, {y}) faces an unknown direction")
        kind = entry.get("kind", "")
        if not isinstance(kind, str) or len(kind) > 20:
            raise GameError(f"the object at ({x}, {y}) has a bad kind")


# --- twist cards: the last lesson round, "make it more fun" ------------------------------


def twists() -> list[dict[str, Any]]:
    """Cards for "make it more fun": one small change each, with code to start from.
    ``needs`` says what must be in the program for the card to count as done."""
    return [
        {
            "id": "speed-up",
            "emoji": "⚡",
            "title": t("Speed-up"),
            "text": t("The critters get faster when you have more points."),
            "code": "if score.value > 3 or ticks() % 2 == 0:\n    self.step()",
            "needs": ["value"],
        },
        {
            "id": "second-critter",
            "emoji": "👯",
            "title": t("A second critter"),
            "text": t("Make one more critter with a different start."),
            "code": 'second = Guard(4, 0, "south")',
            "needs": ["critters2"],
        },
        {
            "id": "power-up",
            "emoji": "⭐",
            "title": t("Power-up"),
            "text": t("An item sends every critter away."),
            "code": (
                "def on_item(item):\n    grab()\n"
                "    for critter in critters():\n        critter.remove()"
            ),
            "needs": ["remove"],
        },
        {
            "id": "secret-door",
            "emoji": "🚪",
            "title": t("Secret door"),
            "text": t("A wall opens when you reach some points."),
            "code": "if score.value == 3:\n    build.clear(4, 1)",
            "needs": ["build"],
        },
    ]


def game_files(root: Path = GAMES_DIR) -> list[Path]:
    return sorted(root.glob("*.json"))


def load_game(path: Path) -> GameSpec:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GameError(f"{path.name}: not valid JSON ({exc})") from None
    try:
        return GameSpec.from_dict(data)
    except ValueError as exc:
        raise GameError(f"{path.name}: {exc}") from None


def find_game(game_id: str, root: Path = GAMES_DIR) -> GameSpec:
    for path in game_files(root):
        if path.stem == game_id:
            return load_game(path)
    raise GameError(f"no game called {game_id!r}")


def all_games(root: Path = GAMES_DIR) -> list[GameSpec]:
    """Every game, the templates in their lesson order: collect, dodge, chase, maze."""
    games = [load_game(path) for path in game_files(root)]
    order = {name: i for i, name in enumerate(TEMPLATES)}
    return sorted(games, key=lambda g: (order.get(g.template, len(order)), g.id))


def game_to_json(spec: GameSpec, animal: str | None = None) -> dict[str, Any]:
    """A game as a client draws it before it starts, in the current language."""
    pack = load_pack(animal if animal in animal_names() else spec.animal)
    world = World.from_spec(spec.world, pack)
    return {
        "id": spec.id,
        "title": spec.title_text(),
        "template": spec.template,
        "animal": pack.id,
        "pack": pack.public(),
        "rules": spec.rules,
        "help": spec.help_lines(),
        "starter": spec.starter,
        "lesson": spec.lesson,
        "maxTicks": spec.max_ticks,
        "tickMs": TICK_MS,
        "keys": list(KEYS),
        "world": {
            **world.to_dict(),
            "walls": sorted([x, y] for x, y in world.walls),
            "objects": spec.objects(),
        },
        "rounds": spec.rounds_text(),
        "twists": twists(),
        "spec": spec.to_dict(),
    }


# --- what programs get -----------------------------------------------------------------


class Score(ZooObject):
    """The game's score: ``score.add(1)``, ``score.value``, ``score.set(0)``."""

    ZOO_ATTRS = ("add", "set", "value")
    KIND = "the score"

    def __init__(self, game: Game) -> None:
        self._game = game
        self.value = 0

    def add(self, points: Any = 1) -> int:
        self.set(self.value + self._points(points))
        return self.value

    def set(self, points: Any) -> int:
        self.value = max(-(10**9), min(10**9, self._points(points)))
        self._game.event({"type": "score", "value": self.value})
        return self.value

    @staticmethod
    def _points(points: Any) -> int:
        if isinstance(points, bool) or not isinstance(points, int):
            raise LearnerError(
                t("The score counts whole numbers, like `score.add(1)`."),
                kind="type",
                exception=TypeError("score needs an int"),
            )
        return points


def _square(game: Game, x: Any, y: Any, command: str) -> tuple[int, int]:
    for value in (x, y):
        if isinstance(value, bool) or not isinstance(value, int):
            raise LearnerError(
                t("`{name}` needs whole numbers for x and y, like `{name}(2, 0)`.", name=command),
                kind="type",
                exception=TypeError("x and y must be ints"),
            )
    if not game.world._inside(x, y):
        raise LearnerError(
            t("({x}, {y}) is outside the world.", x=x, y=y),
            kind="type",
            exception=ValueError("outside the world"),
        )
    return x, y


class Build(ZooObject):
    """Building with code: ``build.block(x, y, "stone")``, ``build.clear(x, y)``,
    ``build.item(x, y)`` and ``build.what(x, y)``. Loops make walls, functions houses."""

    ZOO_ATTRS = ("block", "clear", "item", "what")
    KIND = "the builder"

    def __init__(self, game: Game) -> None:
        self._game = game

    def block(self, x: Any, y: Any, kind: Any = "stone") -> bool:
        """Put a stone (or water, a tree, ice, a bridge) on a square. False when the
        animal or a critter stands there."""
        game = self._game
        x, y = _square(game, x, y, "build.block")
        if kind not in BLOCKS:
            names = ", ".join(f'"{name}"' for name in BLOCKS)
            raise LearnerError(
                t("`build.block` can build: {names}.", names=names),
                kind="type",
                exception=ValueError(f"no block {kind!r}"),
            )
        tile = BLOCKS[kind]
        if tile in (WALL, WATER, TREE) and game.someone_at(x, y):
            game.note(t("Can't build on ({x}, {y}): someone is standing there.", x=x, y=y))
            return False
        return game.set_tile(x, y, tile)

    def clear(self, x: Any, y: Any) -> bool:
        """Make a square plain ground again (it also takes away an item)."""
        x, y = _square(self._game, x, y, "build.clear")
        return self._game.set_tile(x, y, ".")

    def item(self, x: Any, y: Any, name: Any = "") -> bool:
        """Put an item on a square: ``build.item(3, 1)`` or ``build.item(3, 1, "banana")``."""
        game = self._game
        x, y = _square(game, x, y, "build.item")
        tiles = game.pack.items
        if name:
            found = [tile for tile, item in tiles.items() if item == name]
            if not found:
                names = ", ".join(f'"{item}"' for item in tiles.values())
                raise LearnerError(
                    t(
                        "There is no item called {name} here. Items: {names}.",
                        name=repr(name),
                        names=names,
                    ),
                    kind="type",
                    exception=ValueError(f"no item {name!r}"),
                )
            tile = found[0]
        else:
            tile = next(iter(tiles), "B")
        if (x, y) in game.world.walls or game.world.terrain.get((x, y)) in (WATER, TREE):
            game.note(t("Can't put an item on ({x}, {y}): it isn't open.", x=x, y=y))
            return False
        return game.set_tile(x, y, tile)

    def what(self, x: Any, y: Any) -> str:
        """What is on a square: "stone", "water", "tree", "ice", "bridge", an item's name,
        or "" for plain ground."""
        game = self._game
        x, y = _square(game, x, y, "build.what")
        world = game.world
        if (x, y) in world.walls:
            return "stone"
        if (x, y) in world.items:
            return game.pack.item_name(world.items[(x, y)])
        terrain = world.terrain.get((x, y))
        return next((name for name, tile in BLOCKS.items() if tile == terrain), "")


class Door(ZooObject):
    """The doors with one name: ``door("gate").open()``, ``.close()``, ``.toggle()``,
    ``.is_open()``."""

    ZOO_ATTRS = ("open", "close", "toggle", "is_open", "name")
    KIND = "a door"

    def __init__(self, game: Game, name: str) -> None:
        self._game = game
        self.name = name

    def open(self) -> None:
        self._game.set_doors(self.name, True)

    def close(self) -> None:
        self._game.set_doors(self.name, False)

    def toggle(self) -> None:
        self._game.set_doors(self.name, not self.is_open())

    def is_open(self) -> bool:
        return any(d["open"] for d in self._game.doors.values() if d["name"] == self.name)


@dataclass
class PlayerState:
    """One animal of a game with several players (G3). A single game has one."""

    number: int  # 1, 2, ... in the order they joined
    name: str
    x: int
    y: int
    facing: str
    start: tuple[int, int, str]
    look: str = ""  # which animal is drawn: "monkey", "penguin"...
    hidden: bool = False
    touching: set[int] = field(default_factory=set)
    caught: int = 0


@dataclass
class CritterState:
    """Where a critter is. Kept by the game, so a program can't just set ``self.x``."""

    id: int
    x: int
    y: int
    facing: str
    kind: str
    obj: Any
    removed: bool = False


def _direction(value: Any, command: str) -> str:
    if isinstance(value, str):
        if value in DIRECTIONS:
            return value
        if value in KEY_DIRECTION:
            return KEY_DIRECTION[value]
    raise LearnerError(
        t(
            '`{name}` needs a direction: "up", "down", "left", "right" '
            '(or "north", "east", "south", "west").',
            name=command,
        ),
        kind="type",
        exception=ValueError(f"no direction {value!r}"),
    )


def make_critter_class(game: Game) -> type:
    """A fresh ``Critter`` base class for one game. Programs build their own on it:
    ``class Guard(Critter)``. Only its methods are open; its state lives in the game."""

    def __init__(self: Any, x: Any = 0, y: Any = 0, facing: Any = "east", kind: Any = "") -> None:
        game.add_critter(self, x, y, facing, kind)

    def step(self: Any) -> bool:
        """One square ahead; False (and no move) when something is in the way."""
        return game.critter_step(game.state_of(self))

    def turn_left(self: Any) -> None:
        game.critter_turn(game.state_of(self), -1)

    def turn_right(self: Any) -> None:
        game.critter_turn(game.state_of(self), 1)

    def turn_around(self: Any) -> None:
        game.critter_turn(game.state_of(self), 2)

    def face(self: Any, direction: Any) -> None:
        state = game.state_of(self)
        state.facing = _direction(direction, "face")
        game.event({"type": "critter", "id": state.id, "facing": state.facing})

    def wall_ahead(self: Any) -> bool:
        state = game.state_of(self)
        dx, dy = DIRECTIONS[state.facing]
        return not game.open_square(state.x + dx, state.y + dy)

    def remove(self: Any) -> None:
        game.remove_critter(game.state_of(self))

    def position(name: str) -> property:
        return property(lambda self: getattr(game.state_of(self), name))

    namespace: dict[str, Any] = {
        "__init__": __init__,
        "step": step,
        "turn_left": turn_left,
        "turn_right": turn_right,
        "turn_around": turn_around,
        "face": face,
        "wall_ahead": wall_ahead,
        "remove": remove,
        "x": position("x"),
        "y": position("y"),
        "facing": position("facing"),
        "kind": position("kind"),
        "__module__": "zoo",
        "__qualname__": "Critter",
        "__codezoo__": True,
        "__doc__": "Something that moves by itself in a game. Build your own on it.",
    }
    return type("Critter", (), namespace)


# --- a running game --------------------------------------------------------------------


@dataclass
class TickResult:
    tick: int
    events: list[dict[str, Any]]
    lines: list[int]
    output: list[str]
    notes: list[str]
    fired: list[dict[str, Any]] = field(default_factory=list)


class Game:
    """One game being played. ``start()`` runs the setup; then call ``tick(keys)``.

    ``inputs`` records the keys of every tick, which is all it takes to replay the game.
    """

    def __init__(
        self,
        spec: GameSpec,
        source: str,
        *,
        animal: str | None = None,
        seed: int = 0,
        version: tuple[int, int] | None = None,
        budget: int = TICK_BUDGET,
    ) -> None:
        self.spec = spec
        self.source = source
        self.seed = seed
        self.version = version or versions.DEFAULT
        self.budget = budget
        self.pack = load_pack(animal if animal in animal_names() else spec.animal)
        self.world = World.from_spec(spec.world, self.pack)
        self.items_at_start = len(self.world.items)
        self.parsed: ParseResult = parse(source, self.version)
        self.runner: Runner | None = None
        self.critters: dict[int, CritterState] = {}
        self._next_id = 1
        self.score = Score(self)
        self.tick_count = 0
        self.status = PLAYING
        self.message = ""
        self.error: LearnerError | None = None
        self.inputs: list[list[str]] = []
        self.output: list[str] = []
        self.handlers: dict[str, Any] = {}
        self._touching: set[int] = set()
        self._notes: list[str] = []
        self._events: list[dict[str, Any]] = []
        self._printed = 0
        self.build = Build(self)
        self.builds = 0
        self.critter_class: type | None = None
        self._fired: list[dict[str, Any]] = []
        self._sounds = 0
        self.frozen_until = 0
        # doors, switches and power-ups: objects of the world that aren't critters
        self.doors: dict[tuple[int, int], dict[str, Any]] = {}
        self.switches: dict[tuple[int, int], dict[str, Any]] = {}
        self.powers: set[tuple[int, int]] = set()
        for entry in spec.objects():
            square = (entry["at"][0], entry["at"][1])
            if entry.get("type") == "door":
                is_open = bool(entry.get("open", False))
                self.doors[square] = {"name": entry.get("name", "door"), "open": is_open}
                if not is_open:
                    self.world.walls.add(square)
            elif entry.get("type") == "switch":
                self.switches[square] = {"door": entry.get("door", "door"), "on": False}
            elif entry.get("type") == "power":
                self.powers.add(square)

    # --- setup ---------------------------------------------------------------------

    def start(self) -> TickResult:
        """Run the program once: it defines its handlers and makes its critters."""
        if not self.parsed.ok or self.parsed.program is None:
            self.status = BROKEN
            self.message = t("The game can't start: look at the line with the red mark.")
            return TickResult(0, [], [], [], [])
        runner = Runner(
            self.parsed.program,
            self.actions(),
            self.world.drain_events,
            SETUP_STEPS,
            version=self.version,
            seed=self.seed,
        )
        self.runner = runner
        self.world.runner = runner
        runner.execute()
        if runner.error is not None:
            self._fail(runner.error)
        else:
            self._find_handlers()
            if self.status == PLAYING:
                self._make_objects()
        return self._finish_tick()

    def actions(self) -> dict[str, Callable[..., Any]]:
        found = {name: self._no_crash(action) for name, action in self.world.actions().items()}
        # a game's code works with every animal: `grab()` also for the penguin's `catch()`
        for neutral in NEUTRAL_ACTIONS:
            found.setdefault(neutral, self._no_crash(getattr(self.world, neutral)))
        self.critter_class = make_critter_class(self)
        found |= {
            "Critter": self.critter_class,
            "score": self.score,
            "win": self.win,
            "lose": self.lose,
            "go": self.go,
            "where": self.where,
            "ticks": self.ticks,
            "critters": self.critter_list,
            "build": self.build,  # in a game, building with code (the beaver's trick waits)
            "player": self.player,
            "animals": self.animals,
            "door": self.door,
            "sound": self.sound,
        }
        return found

    def _make_objects(self) -> None:
        """The world's objects: one of the program's critters on each, ``Guard(x, y)``."""
        assert self.runner is not None
        for entry in self.spec.objects():
            if entry.get("type"):
                continue  # doors, switches and power-ups belong to the world
            x, y = entry["at"]
            name = entry["class"]
            cls = self.runner.globals.get(name)
            base = self.critter_class
            if not (isinstance(cls, type) and base is not None and issubclass(cls, base)):
                self.note(
                    t(
                        "The world has a {name} at ({x}, {y}), but the code has no "
                        "`class {name}(Critter)`, so it just stands there.",
                        name=name,
                        x=x,
                        y=y,
                    )
                )
                cls = base
            try:
                made = self.runner._call_value(cls, [x, y], {}, name)
            except LearnerError as exc:
                self._fail(exc)
                return
            except RecursionError:
                self._fail(
                    LearnerError(
                        t("Your program went too deep for the zoo to follow."), kind="too_deep"
                    )
                )
                return
            state = next((s for s in self.critters.values() if s.obj is made), None)
            if state is None:
                continue  # its __init__ forgot super().__init__: state_of says so when used
            if entry.get("facing"):
                state.facing = entry["facing"]
            if entry.get("kind"):
                state.kind = entry["kind"]
            if (state.x, state.y) != (x, y):
                state.x, state.y = x, y
            self.event(
                {
                    "type": "critter",
                    "id": state.id,
                    "at": [x, y],
                    "facing": state.facing,
                    "kind": state.kind,
                }
            )

    def note(self, text: str) -> None:
        """A kind remark in the output (a bump, a build that didn't fit)."""
        self._notes.append(text)

    # --- reading the program: what the lesson rounds look for ------------------------

    def features(self) -> list[str]:
        """What the program has, for the lesson rounds: its handlers, its critters, and
        every name it uses (``score``, ``win``, ``remove``...)."""
        found = set(self.handlers)
        alive = [s for s in self.critters.values() if not s.removed]
        if alive:
            found.add("critter")
        if len(alive) >= 2:
            found.add("critters2")
        if any(self._plain_function(getattr(type(s.obj), "on_tick", None)) for s in alive):
            found.add("critter_tick")
        if self.spec.objects() and self.runner is not None:
            base = self.critter_class
            for entry in self.spec.objects():
                cls = self.runner.globals.get(entry.get("class", ""))
                if isinstance(cls, type) and base is not None and issubclass(cls, base):
                    found.add("object")
        if self.doors:
            found.add("doors")
        found |= source_names(self.source)
        return sorted(found)

    def _no_crash(self, action: Callable[..., Any]) -> Callable[..., Any]:
        """In a game a bump stops the animal, not the program."""
        if isinstance(action, type):
            return action

        def safe(*args: Any, **kwargs: Any) -> Any:
            try:
                return action(*args, **kwargs)
            except LearnerError as exc:
                if exc.kind != "bump" or exc.exception is not None:
                    raise
                self._notes.append(exc.message)
                return None

        safe.__name__ = getattr(action, "__name__", "action")
        return safe

    def _find_handlers(self) -> None:
        assert self.runner is not None
        for name in HANDLERS:
            handler = self.runner.globals.get(name)
            if handler is None:
                continue
            if not self._plain_function(handler):
                self._fail(
                    LearnerError(
                        t("`{name}` must be a plain function: `def {name}(...):`.", name=name),
                        kind="type",
                    )
                )
                return
            self.handlers[name] = handler

    def _plain_function(self, value: Any) -> bool:
        assert self.runner is not None
        return isinstance(value, interpreter.function) and self.runner._kind(value.node) == (
            "function"
        )

    # --- commands for programs ---------------------------------------------------

    def win(self, text: Any = "") -> None:
        if self.status == PLAYING:
            self.status = WON
            self.message = str(text)[:200] or t("You won!")
            self.event({"type": "win", "text": self.message})

    def lose(self, text: Any = "") -> None:
        if self.status == PLAYING:
            self.status = LOST
            self.message = str(text)[:200] or t("Game over.")
            self.event({"type": "lose", "text": self.message})

    def go(self, direction: Any) -> None:
        """Face ``direction`` and take one step (no bump: the animal just stays)."""
        facing = _direction(direction, "go")
        if self.world.facing != facing:
            self.world.facing = facing
            self.world.events.append({"type": "turn", "facing": facing})
        self._no_crash(self.world.step)()

    def where(self) -> tuple[int, int]:
        """Where the animal is: ``(x, y)``."""
        return (self.world.x, self.world.y)

    def ticks(self) -> int:
        return self.tick_count

    def critter_list(self) -> list[Any]:
        return [state.obj for state in self.critters.values() if not state.removed]

    def door(self, name: Any = "door") -> Door:
        """The world's doors called ``name``: ``door("gate").open()``."""
        if not any(d["name"] == name for d in self.doors.values()):
            names = ", ".join(sorted({f'"{d["name"]}"' for d in self.doors.values()}))
            raise LearnerError(
                t(
                    "This world has no door called {name}. Doors: {names}.",
                    name=repr(name),
                    names=names or t("none"),
                ),
                kind="type",
                exception=ValueError(f"no door {name!r}"),
            )
        return Door(self, name)

    def set_doors(self, name: str, is_open: bool) -> None:
        for square, found in self.doors.items():
            if found["name"] != name or found["open"] == is_open:
                continue
            if not is_open and self.someone_at(*square):
                self.note(
                    t(
                        "The door at ({x}, {y}) can't close: someone is in it.",
                        x=square[0],
                        y=square[1],
                    )
                )
                continue
            found["open"] = is_open
            if is_open:
                self.world.walls.discard(square)
            else:
                self.world.walls.add(square)
            self.event({"type": "door", "at": list(square), "open": is_open})

    def sound(self, name: Any = "ding") -> None:
        """Play a sound on the player's device: ``sound("ding")``."""
        if name not in SOUNDS:
            names = ", ".join(f'"{found}"' for found in SOUNDS)
            raise LearnerError(
                t("`sound` knows these sounds: {names}.", names=names),
                kind="type",
                exception=ValueError(f"no sound {name!r}"),
            )
        if self._sounds < MAX_SOUNDS:
            self._sounds += 1
            self.event({"type": "sound", "name": name})

    def player(self) -> int:
        """Which player's animal the handler is moving: 1 in a game for one."""
        return 1

    def animals(self) -> list[tuple[int, int]]:
        """Where every player's animal is: ``[(x, y), ...]`` (one in a game for one)."""
        return [(self.world.x, self.world.y)]

    def animal_squares(self) -> set[tuple[int, int]]:
        return {(self.world.x, self.world.y)}

    def someone_at(self, x: int, y: int) -> bool:
        return (x, y) in self.animal_squares() or any(
            (s.x, s.y) == (x, y) and not s.removed for s in self.critters.values()
        )

    # --- building with code ------------------------------------------------------

    def set_tile(self, x: int, y: int, tile: str) -> bool:
        """Change one square: "." plain, "#" stone, terrain, or an item's capital letter."""
        if self.builds >= MAX_BUILDS:
            raise LearnerError(
                t(
                    "The builder is tired: a game can change at most {count} squares.",
                    count=MAX_BUILDS,
                ),
                kind="type",
            )
        self.builds += 1
        world = self.world
        square = (x, y)
        self.doors.pop(square, None)  # building over a door, switch or power-up removes it
        self.switches.pop(square, None)
        self.powers.discard(square)
        world.walls.discard(square)
        world.terrain.pop(square, None)
        world.items.pop(square, None)
        if tile == WALL:
            world.walls.add(square)
        elif tile.isalpha() and tile.isupper():
            world.items[square] = tile
            self.items_at_start += 1
        elif tile != ".":
            world.terrain[square] = tile
        self.event({"type": "tile", "at": [x, y], "tile": tile})
        return True

    # --- critters -----------------------------------------------------------------

    def add_critter(self, obj: Any, x: Any, y: Any, facing: Any, kind: Any) -> None:
        if any(state.obj is obj for state in self.critters.values()):
            return  # __init__ ran twice (a subclass calling super().__init__ again)
        if sum(not s.removed for s in self.critters.values()) >= MAX_CRITTERS:
            raise LearnerError(
                t("A game can have at most {count} critters.", count=MAX_CRITTERS),
                kind="type",
            )
        for value, name in ((x, "x"), (y, "y")):
            if isinstance(value, bool) or not isinstance(value, int):
                raise LearnerError(
                    t("A critter's `{name}` must be a whole number.", name=name),
                    kind="type",
                    exception=TypeError(f"{name} must be an int"),
                )
        if not self.world._inside(x, y) or not self.open_square(x, y, critters=False):
            raise LearnerError(
                t("A critter can't start at ({x}, {y}): that square isn't open.", x=x, y=y),
                kind="type",
                exception=ValueError("square not open"),
            )
        state = CritterState(
            self._next_id,
            x,
            y,
            _direction(facing, "Critter"),
            str(kind)[:20] or type(obj).__name__.lower(),
            obj,
        )
        self._next_id += 1
        self.critters[state.id] = state
        self.event(
            {
                "type": "critter",
                "id": state.id,
                "new": True,
                "at": [x, y],
                "facing": state.facing,
                "kind": state.kind,
            }
        )

    def state_of(self, obj: Any) -> CritterState:
        for state in self.critters.values():
            if state.obj is obj:
                if state.removed:
                    raise LearnerError(t("That critter was removed from the game."), kind="type")
                return state
        raise LearnerError(
            t(
                "This critter was never put in the game. In your own `__init__`, call "
                "`super().__init__(x, y)` first."
            ),
            kind="type",
        )

    def open_square(self, x: int, y: int, *, critters: bool = True) -> bool:
        world = self.world
        if not world._inside(x, y) or (x, y) in world.walls:
            return False
        if world.terrain.get((x, y)) in (WATER, TREE):
            return False
        return not (
            critters
            and any(s.x == x and s.y == y and not s.removed for s in self.critters.values())
        )

    def critter_step(self, state: CritterState) -> bool:
        dx, dy = DIRECTIONS[state.facing]
        x, y = state.x + dx, state.y + dy
        if not self.open_square(x, y):
            self.event({"type": "critter", "id": state.id, "bump": True})
            return False
        self.event({"type": "critter", "id": state.id, "from": [state.x, state.y], "to": [x, y]})
        state.x, state.y = x, y
        return True

    def critter_turn(self, state: CritterState, quarter_turns: int) -> None:
        state.facing = CLOCKWISE[(CLOCKWISE.index(state.facing) + quarter_turns) % 4]
        self.event({"type": "critter", "id": state.id, "facing": state.facing})

    def remove_critter(self, state: CritterState) -> None:
        state.removed = True
        self.event({"type": "critter", "id": state.id, "removed": True})

    def event(self, data: dict[str, Any]) -> None:
        # into the world's own list, so events keep their order with the animal's
        self.world.events.append(data)

    # --- ticks ------------------------------------------------------------------------

    def tick(self, keys: list[str] | None = None) -> TickResult:
        """One tick: keys, then ``on_tick`` (the program's, then each critter's), then
        items and touches, then the rules."""
        if self.status != PLAYING:
            return self._finish_tick()
        assert self.runner is not None
        pressed = clean_keys(keys)
        self.inputs.append(pressed)
        self._begin_tick()
        start = (self.world.x, self.world.y)
        self._keys(pressed)
        self._tick_handlers()
        self._arrivals(start)
        self._touching = self._touches(self._touching)
        self._rules()
        return self._finish_tick()

    def _begin_tick(self, budget: int | None = None) -> None:
        assert self.runner is not None
        self.tick_count += 1
        self.runner.max_steps = self.runner.count + (budget or self.budget)
        self.runner.top_current = None  # a traceback starts at the handler, not the setup

    def _keys(self, pressed: list[str]) -> None:
        for key in pressed:
            if "on_key" in self.handlers:
                self._call(self.handlers["on_key"], [key], "on_key")
            elif key in KEY_DIRECTION:
                self.go(key)

    def _tick_handlers(self) -> None:
        if "on_tick" in self.handlers:
            self._call(self.handlers["on_tick"], [], "on_tick")
        if self.tick_count < self.frozen_until:
            return  # a power-up froze the critters
        for state in list(self.critters.values()):
            if state.removed or self.status != PLAYING:
                continue
            handler = getattr(type(state.obj), "on_tick", None)
            if self._plain_function(handler):
                self._call(handler, [state.obj], f"{type(state.obj).__name__}.on_tick")

    def _call(self, handler: Any, args: list[Any], name: str) -> None:
        if self.status != PLAYING:
            return
        assert self.runner is not None
        before = self._snapshot()
        steps = self.runner.count
        try:
            self.runner.invoke(handler, args, {})
        except LearnerError as exc:
            if exc.kind == "too_many_steps" and self.runner.count > self.runner.max_steps:
                exc.message = t(
                    "The game got tired: `{name}` took more than {count} steps in one tick. "
                    "Is a loop running forever?",
                    name=name,
                    count=self.budget,
                )
            self._fail(exc)
        except RecursionError:
            deep = t("Your program went too deep for the zoo to follow.")
            self._fail(LearnerError(deep, kind="too_deep"))
        except interpreter._Signal:
            odd = t("`{name}` stopped in a way the zoo can't follow.", name=name)
            self._fail(LearnerError(odd))
        self._log(name, before, self.runner.count - steps)

    def _snapshot(self) -> dict[str, Any]:
        """What a handler can change, to say afterwards what it did change."""
        world = self.world
        return {
            "animal": (world.x, world.y, world.facing),
            "score": self.score.value,
            "items": len(world.items),
            "critters": tuple(
                (s.id, s.x, s.y, s.facing, s.removed) for s in self.critters.values()
            ),
            "world": self.builds,
            "doors": tuple(d["open"] for d in self.doors.values()),
            "status": self.status,
            "printed": len(self.runner.output) if self.runner else 0,
            "said": len(world.said),
            "sounds": self._sounds,
        }

    def _log(self, name: str, before: dict[str, Any], steps: int) -> None:
        after = self._snapshot()
        changes = [key for key, value in before.items() if after[key] != value]
        changes = ["printed" if key == "said" else key for key in changes]
        for entry in self._fired:
            if entry["handler"] == name:  # every critter's on_tick: one line, counted
                entry["times"] += 1
                entry["steps"] += steps
                entry["changes"] = sorted(set(entry["changes"]) | set(changes))
                return
        self._fired.append(
            {"handler": name, "times": 1, "steps": steps, "changes": sorted(set(changes))}
        )

    def _arrivals(self, start: tuple[int, int]) -> None:
        here = (self.world.x, self.world.y)
        if here == start:
            return
        tile = self.world.items.get(here)
        if tile is not None and "on_item" in self.handlers:
            self._call(self.handlers["on_item"], [self.pack.item_name(tile)], "on_item")
        switch = self.switches.get(here)
        if switch is not None and self.status == PLAYING:
            switch["on"] = not switch["on"]
            self.event({"type": "switch", "at": list(here), "on": switch["on"]})
            name = switch["door"]
            if any(d["name"] == name for d in self.doors.values()):
                self.set_doors(name, not Door(self, name).is_open())
            if "on_switch" in self.handlers:
                self._call(self.handlers["on_switch"], [name], "on_switch")
        if here in self.powers and self.status == PLAYING:
            self.powers.discard(here)
            self.event({"type": "power", "at": list(here)})
            if "on_power" in self.handlers:
                self._call(self.handlers["on_power"], [], "on_power")
            else:
                self.frozen_until = self.tick_count + FREEZE_TICKS
                self.note(t("Power-up! The critters freeze for {count} ticks.", count=FREEZE_TICKS))

    def _touches(self, before: set[int]) -> set[int]:
        """Critters that just met the animal (``before``: those already touching it)."""
        here = (self.world.x, self.world.y)
        touching = {s.id for s in self.critters.values() if not s.removed and (s.x, s.y) == here}
        for critter_id in sorted(touching - before):
            if self.status != PLAYING:
                break
            state = self.critters[critter_id]
            if state.removed:
                continue
            self.event({"type": "touch", "id": critter_id, "at": list(here)})
            if "on_touch" in self.handlers:
                self._call(self.handlers["on_touch"], [state.obj], "on_touch")
            elif self.spec.rules.get("caught"):
                self.caught()
        return touching

    def caught(self) -> None:
        """The ``caught`` rule: a critter met the animal and the program has no ``on_touch``."""
        self.lose(t("A critter caught the {animal}!", animal=self.pack.animal_name()))

    def _rules(self) -> None:
        if self.status != PLAYING:
            return
        win = self.spec.rules.get("win")
        if win == "collect_all" and self.items_at_start and not self.world.items:
            self.win(t("Every item collected!"))
        elif isinstance(win, dict) and "score" in win and self.score.value >= win["score"]:
            self.win(t("{count} points!", count=self.score.value))
        elif isinstance(win, dict) and "survive" in win and self.tick_count >= win["survive"]:
            self.win(t("You made it to the end!"))
        if self.status == PLAYING and self.tick_count >= self.spec.max_ticks:
            self.status = OVER
            self.message = t("Time's up!")
            self.event({"type": "over", "text": self.message})

    def _fail(self, error: LearnerError) -> None:
        if error.exception is not None and error.kind == "raised" and self.runner is not None:
            error.message = self.runner._uncaught_message(error)
        self.error = error
        self.status = BROKEN
        self.message = error.message

    def _finish_tick(self) -> TickResult:
        lines: list[int] = []
        events: list[dict[str, Any]] = []
        if self.runner is not None:
            for step in self.runner.steps:
                events.extend(step.events)
                line = self.line_of(step.node_id)
                if line is not None and line not in lines and len(lines) < MAX_LINES:
                    lines.append(line)
            self.runner.steps.clear()
            output = self.runner.output[self._printed :]
            self._printed = len(self.runner.output)
            if len(self.runner.output) > MAX_OUTPUT:
                del self.runner.output[: len(self.runner.output) - MAX_OUTPUT]
                self._printed = len(self.runner.output)
        else:
            output = []
        events.extend(self.world.drain_events())
        self.output = (self.output + output)[-MAX_OUTPUT:]
        notes, self._notes = self._notes, []
        fired, self._fired = self._fired, []
        self._sounds = 0
        return TickResult(self.tick_count, events, lines, output, notes, fired)

    def line_of(self, node_id: str | None) -> int | None:
        span = self.parsed.positions.get(node_id or "")
        return span.line if span else None

    # --- reading the game ------------------------------------------------------

    def state(self) -> dict[str, Any]:
        world = self.world
        return {
            "tick": self.tick_count,
            "status": self.status,
            "message": self.message,
            "score": self.score.value,
            "animal": {"at": [world.x, world.y], "facing": world.facing},
            "items": [[x, y, tile] for (x, y), tile in sorted(world.items.items())],
            "terrain": [[x, y, kind] for (x, y), kind in sorted(world.terrain.items())],
            # closed doors block like stones but are drawn as doors
            "walls": sorted([x, y] for x, y in world.walls if (x, y) not in self.doors),
            "doors": [[x, y, d["open"]] for (x, y), d in sorted(self.doors.items())],
            "switches": [[x, y, sw["on"]] for (x, y), sw in sorted(self.switches.items())],
            "powers": sorted([x, y] for x, y in self.powers),
            "frozen": max(0, self.frozen_until - self.tick_count),
            "critters": [
                {"id": s.id, "at": [s.x, s.y], "facing": s.facing, "kind": s.kind}
                for s in self.critters.values()
                if not s.removed
            ],
            "said": world.said[-1] if world.said else "",
        }

    def error_json(self) -> dict[str, Any] | None:
        if self.error is None:
            return None
        return {
            "message": self.error.message,
            "kind": self.error.kind,
            "line": self.line_of(self.error.node_id),
            "traceback": [
                {"function": name, "line": self.line_of(node)}
                for name, node in self.error.traceback
            ],
        }

    def to_json(self, result: TickResult) -> dict[str, Any]:
        return {
            "state": self.state(),
            "events": result.events,
            "lines": result.lines,
            "output": result.output,
            "notes": result.notes,
            "error": self.error_json(),
            "diagnostics": [vars(d) for d in self.parsed.diagnostics],
            "handlers": sorted(self.handlers),
            "fired": result.fired,
            "features": self.features() if result.tick == 0 else None,
        }


def clean_keys(keys: Any) -> list[str]:
    return [key for key in (keys or []) if key in KEYS][:MAX_KEYS]


def source_names(source: str) -> set[str]:
    """Every name in the code (``score``, ``remove``...), without running it. Code that
    doesn't tokenize (a half-typed line) gives the names before the problem."""
    names: set[str] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                names.add(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return names


def play(
    spec: GameSpec,
    source: str,
    keys: list[list[str]],
    *,
    seed: int = 0,
    animal: str | None = None,
    budget: int = TICK_BUDGET,
) -> Game:
    """Play a whole game without a screen: one list of keys per tick (replays, tests,
    the playtest bot). Stops early when the game ends."""
    game = Game(spec, source, seed=seed, animal=animal, budget=budget)
    game.start()
    for pressed in keys:
        if game.status != PLAYING:
            break
        game.tick(pressed)
    return game


# --- "Test my game": the playtest bot ------------------------------------------------

BOT_KINDS = ("collector", "chaser", "wanderer")
BOT_MAX_TICKS = 600
ARROWS = {"north": "up", "east": "right", "south": "down", "west": "left"}


def _walkable(game: Game, x: int, y: int, *, doors: bool = False) -> bool:
    """A square the animal can walk on (``doors``: count closed doors as open, for "can
    anyone ever get there")."""
    world = game.world
    if not world._inside(x, y):
        return False
    if (x, y) in world.walls and not (doors and (x, y) in game.doors):
        return False
    return world.terrain.get((x, y)) not in (WATER, TREE, THIN_ICE, "o")


def _neighbours(x: int, y: int) -> list[tuple[str, int, int]]:
    return [(d, x + dx, y + dy) for d, (dx, dy) in DIRECTIONS.items()]


def _reachable(game: Game, start: tuple[int, int]) -> set[tuple[int, int]]:
    seen = {start}
    todo = [start]
    while todo:
        x, y = todo.pop()
        for _, nx, ny in _neighbours(x, y):
            if (nx, ny) not in seen and _walkable(game, nx, ny, doors=True):
                seen.add((nx, ny))
                todo.append((nx, ny))
    return seen


def _first_step(
    game: Game, here: tuple[int, int], targets: set[tuple[int, int]], avoid: set[tuple[int, int]]
) -> str | None:
    """The first direction of a shortest walk to any target, around ``avoid``."""
    if not targets:
        return None
    first: dict[tuple[int, int], str] = {here: ""}
    todo = [here]
    for square in todo:  # breadth first: the list grows while it is walked
        if square in targets and square != here:
            return first[square]
        for direction, nx, ny in _neighbours(*square):
            nxt = (nx, ny)
            if nxt in first or not _walkable(game, nx, ny):
                continue
            if nxt in avoid and nxt not in targets:
                continue
            first[nxt] = first[square] or direction
            todo.append(nxt)
    return None


def _bot_key(game: Game, kind: str, rng: random.Random) -> str:
    keys = list(KEY_DIRECTION)
    if kind == "chaser" and game.spec.rules.get("caught"):
        kind = "collector"  # meeting a critter loses: even a chaser keeps away
    if kind == "wanderer" or rng.random() < 0.15:
        return "space" if rng.random() < 0.05 else rng.choice(keys)
    here = (game.world.x, game.world.y)
    foes = {(s.x, s.y) for s in game.critters.values() if not s.removed}
    danger = foes | {(nx, ny) for x, y in foes for _, nx, ny in _neighbours(x, y)}
    items = set(game.world.items)
    if kind == "collector" and not items and foes:
        # nothing to collect: keep away from the critters
        def distance(square: tuple[int, int]) -> int:
            return min(abs(square[0] - fx) + abs(square[1] - fy) for fx, fy in foes)

        options = [
            (distance((nx, ny)), d) for d, nx, ny in _neighbours(*here) if _walkable(game, nx, ny)
        ]
        if options:
            best = max(score for score, _ in options)
            return ARROWS[rng.choice([d for score, d in options if score == best])]
    targets = items if kind == "collector" or items else foes
    avoid = danger if kind == "collector" else set()
    direction = _first_step(game, here, targets, avoid) or _first_step(game, here, targets, set())
    if direction is None and game.switches:  # stuck: try a switch, it may open a door
        switches = set(game.switches) - {here}
        direction = _first_step(game, here, switches, set())
    return ARROWS[direction] if direction else rng.choice(keys)


def playtest(
    spec: GameSpec,
    source: str,
    *,
    games: int = BOT_GAMES,
    ticks: int = BOT_TICKS,
    animal: str | None = None,
    seconds: float | None = None,
) -> dict[str, Any]:
    """Bot animals play the game ``games`` times and say, kindly, how it went: "Nobody
    could win: the critters caught every bot", "Every bot won in 3 ticks: too easy?",
    "No one can reach the banana at (4, 0)". Deterministic: bot ``i`` uses seed ``i``.
    ``seconds`` stops early on a slow device (the report says how many were played)."""
    games = max(1, min(MAX_BOT_GAMES, games))
    win = spec.rules.get("win")
    survive = win.get("survive", 0) if isinstance(win, dict) else 0
    limit = min(spec.max_ticks, BOT_MAX_TICKS, max(ticks, survive))
    first = Game(spec, source, animal=animal)
    first.start()
    report: dict[str, Any] = {
        "played": 0,
        "won": 0,
        "lost": 0,
        "playing": 0,
        "broken": 0,
        "winTicks": None,
        "bestScore": 0,
        "ticks": limit,
        "unreachable": [],
        "messages": [],
    }
    messages: list[dict[str, str]] = report["messages"]
    if first.status == BROKEN:
        messages.append({"kind": "err", "text": first.message})
        report["error"] = first.error_json()
        return report
    if win == "collect_all":
        reach = _reachable(first, (first.world.x, first.world.y))
        for (x, y), tile in sorted(first.world.items.items()):
            if (x, y) not in reach:
                report["unreachable"].append([x, y])
                messages.append(
                    {
                        "kind": "warn",
                        "text": t(
                            "No one can reach the {item} at ({x}, {y}).",
                            item=first.pack.item_name(tile),
                            x=x,
                            y=y,
                        ),
                    }
                )
    stop_at = time.monotonic() + seconds if seconds else None
    win_ticks: list[int] = []
    broke: dict[str, Any] | None = None
    for number in range(games):
        game = first if number == 0 else Game(spec, source, animal=animal, seed=number)
        if number:
            game.start()
        rng = random.Random(number * 7919 + 1)
        kind = BOT_KINDS[number % len(BOT_KINDS)]
        while game.status == PLAYING and game.tick_count < limit:
            game.tick([_bot_key(game, kind, rng)])
        report["played"] += 1
        report["bestScore"] = max(report["bestScore"], game.score.value)
        if game.status == WON:
            report["won"] += 1
            win_ticks.append(game.tick_count)
        elif game.status == LOST:
            report["lost"] += 1
        elif game.status == BROKEN:
            report["broken"] += 1
            if broke is None:
                broke = {
                    "ticks": game.tick_count,
                    "message": game.message,
                    "error": game.error_json(),
                }
        else:
            report["playing"] += 1
        if stop_at is not None and time.monotonic() > stop_at:
            break
    played = report["played"]
    if win_ticks:
        report["winTicks"] = sorted(win_ticks)[len(win_ticks) // 2]
    if broke is not None:
        report["error"] = broke["error"]
        messages.append(
            {
                "kind": "err",
                "text": t(
                    "The game broke for {count} of {games} bots, "
                    "the first after {ticks} ticks: {message}",
                    count=report["broken"],
                    games=played,
                    ticks=broke["ticks"],
                    message=broke["message"],
                ),
            }
        )
    can_win = win is not None or "win" in first.features()
    if broke is not None and report["broken"] == played:
        pass  # every game broke: that is the one thing to fix
    elif not can_win:
        messages.append(
            {
                "kind": "warn",
                "text": t(
                    "Nobody can win yet: give the game a way to win, like `win()` in a handler."
                ),
            }
        )
    elif not report["won"]:
        if report["lost"] > played // 2:
            text = t(
                "Nobody could win: the critters caught {count} of {games} bots. "
                "Maybe they are too fast?",
                count=report["lost"],
                games=played,
            )
        else:
            text = t(
                "Nobody could win in {ticks} ticks. Maybe it is too hard, or too far?", ticks=limit
            )
        messages.append({"kind": "warn", "text": text})
    elif report["won"] * 5 < played:
        messages.append(
            {
                "kind": "warn",
                "text": t(
                    "Only {won} of {games} bots won: a hard game. Is that what you want?",
                    won=report["won"],
                    games=played,
                ),
            }
        )
    elif report["won"] == played and report["winTicks"] is not None and report["winTicks"] <= 15:
        messages.append(
            {
                "kind": "warn",
                "text": t(
                    "Every bot won in about {ticks} ticks: too easy?", ticks=report["winTicks"]
                ),
            }
        )
    else:
        messages.append(
            {
                "kind": "ok",
                "text": t(
                    "{won} of {games} bots won, in about {ticks} ticks. Sounds like a fair game!",
                    won=report["won"],
                    games=played,
                    ticks=report["winTicks"],
                ),
            }
        )
    if (
        report["lost"] == 0
        and report["won"]
        and (spec.rules.get("caught") or "lose" in first.features())
    ):
        messages.append({"kind": "ok", "text": t("No bot lost. Is it scary enough?")})
    if played < games:
        messages.append(
            {
                "kind": "ok",
                "text": t("This device is slow, so only {count} games were played.", count=played),
            }
        )
    return report


# --- running games between requests --------------------------------------------------


class Sessions:
    """The games being played on this server (or in this web worker), by session id.

    Only the newest ``limit`` are kept; an old tab's game is simply forgotten.
    """

    def __init__(self, limit: int = 32) -> None:
        self.limit = limit
        self._games: OrderedDict[str, Game] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, game: Game) -> str:
        session = secrets.token_hex(8)
        with self._lock:
            self._games[session] = game
            while len(self._games) > self.limit:
                self._games.popitem(last=False)
        return session

    def get(self, session: Any) -> Game | None:
        with self._lock:
            game = self._games.get(session) if isinstance(session, str) else None
            if game is not None:
                self._games.move_to_end(session)
            return game

    def stop(self, session: Any) -> None:
        with self._lock:
            if isinstance(session, str):
                self._games.pop(session, None)


SESSIONS = Sessions()
