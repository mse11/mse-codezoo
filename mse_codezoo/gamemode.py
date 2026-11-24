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
"""

from __future__ import annotations

import json
import secrets
import threading
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
from mse_codezoo.world import CLOCKWISE, DIRECTIONS, TREE, WATER, World

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
HANDLERS = ("on_key", "on_tick", "on_item", "on_touch")
WIN_RULES = ("collect_all", "score", "survive")
PLAYING, WON, LOST, OVER, BROKEN = "playing", "won", "lost", "over", "error"


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
        if not isinstance(help_, dict):
            raise GameError("help must map a language to a list of lines")
        spec = cls(
            id=game_id,
            title=dict(title),
            world=world,
            animal=animal,
            template=str(data.get("template", "")),
            rules=dict(rules),
            starter=str(data.get("starter", "")),
            help={k: [str(line) for line in v] for k, v in help_.items()},
            max_ticks=max_ticks,
        )
        World.from_spec(world, load_pack(animal))  # raises ValueError on a bad world
        return spec

    def title_text(self) -> str:
        return self.title.get(current()) or self.title.get("en") or self.id

    def help_lines(self) -> list[str]:
        return self.help.get(current()) or self.help.get("en") or []


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
    return [load_game(path) for path in game_files(root)]


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
        "maxTicks": spec.max_ticks,
        "tickMs": TICK_MS,
        "keys": list(KEYS),
        "world": {**world.to_dict(), "walls": sorted([x, y] for x, y in world.walls)},
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
        return self._finish_tick()

    def actions(self) -> dict[str, Callable[..., Any]]:
        found = {name: self._no_crash(action) for name, action in self.world.actions().items()}
        found |= {
            "Critter": make_critter_class(self),
            "score": self.score,
            "win": self.win,
            "lose": self.lose,
            "go": self.go,
            "where": self.where,
            "ticks": self.ticks,
            "critters": self.critter_list,
        }
        return found

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
        pressed = [key for key in (keys or []) if key in KEYS][:MAX_KEYS]
        self.inputs.append(pressed)
        self.tick_count += 1
        self.runner.max_steps = self.runner.count + self.budget
        self.runner.top_current = None  # a traceback starts at the handler, not the setup
        start = (self.world.x, self.world.y)
        for key in pressed:
            if "on_key" in self.handlers:
                self._call(self.handlers["on_key"], [key], "on_key")
            elif key in KEY_DIRECTION:
                self.go(key)
        if "on_tick" in self.handlers:
            self._call(self.handlers["on_tick"], [], "on_tick")
        for state in list(self.critters.values()):
            if state.removed or self.status != PLAYING:
                continue
            handler = getattr(type(state.obj), "on_tick", None)
            if self._plain_function(handler):
                self._call(handler, [state.obj], f"{type(state.obj).__name__}.on_tick")
        self._arrivals(start)
        self._touches()
        self._rules()
        return self._finish_tick()

    def _call(self, handler: Any, args: list[Any], name: str) -> None:
        if self.status != PLAYING:
            return
        assert self.runner is not None
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

    def _arrivals(self, start: tuple[int, int]) -> None:
        here = (self.world.x, self.world.y)
        tile = self.world.items.get(here)
        if here != start and tile is not None and "on_item" in self.handlers:
            self._call(self.handlers["on_item"], [self.pack.item_name(tile)], "on_item")

    def _touches(self) -> None:
        here = (self.world.x, self.world.y)
        touching = {s.id for s in self.critters.values() if not s.removed and (s.x, s.y) == here}
        for critter_id in sorted(touching - self._touching):
            if self.status != PLAYING:
                break
            state = self.critters[critter_id]
            self.event({"type": "touch", "id": critter_id, "at": list(here)})
            if "on_touch" in self.handlers:
                self._call(self.handlers["on_touch"], [state.obj], "on_touch")
            elif self.spec.rules.get("caught"):
                self.lose(t("A critter caught the {animal}!", animal=self.pack.animal_name()))
        self._touching = touching

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
        return TickResult(self.tick_count, events, lines, output, notes)

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
        }


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
