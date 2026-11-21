"""Grid world: the animal, walls and items, and the neutral actions that change them.

Actions append events (``move``, ``turn``, ``grab``, ``say``, ``bump``, ``sense`` and the
tricks' ``swing``, ``climb``, ``crack``, ``build``, ``hide``) that clients animate. Sensors
(``is_blocked()``, ``item_here()``, ``item_ahead()``) answer questions about the world, so
programs can make decisions. Animal packs rename actions, name the animal, its world and
its items in each language, and switch on the animal's own tricks; the world stays neutral.

Tiles: ``.`` ground, ``#`` rock, ``A``-``Z`` items, and terrain that tricks use:
``~`` water or a gap, ``t`` tree, ``-`` thin ice, ``o`` a spot a guard watches,
``=`` a log bridge. Items can also sit on terrain (a coconut up a tree) through the
world's ``items`` list.

Some tricks take time: the octopus's ``await reach(arm)`` stretches one of its eight arms
while the other arms keep working, and ``stretch(arm)`` does the same for threads. A world
can also hold answers for ``input()`` (``inputs``), files for ``open()`` (``data``) and
whether threads share the GIL (``gil``). Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mse_codezoo.i18n import current, plural, t
from mse_codezoo.interpreter import Awaitable, LearnerError

DIRECTIONS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
CLOCKWISE = ["north", "east", "south", "west"]
ARROWS = {"north": "^", "east": ">", "south": "v", "west": "<"}
EMPTY = "."
WALL = "#"
WATER = "~"
TREE = "t"
THIN_ICE = "-"
WATCHED = "o"
BRIDGE = "="
TERRAIN = (WATER, TREE, THIN_ICE, WATCHED, BRIDGE)
MOVES = ("step", "turn_left", "turn_right", "grab", "say")
SENSORS = ("is_blocked", "item_here", "item_ahead")
NEUTRAL_ACTIONS = MOVES + SENSORS
TRICKS = (
    "swing",
    "climb",
    "slide",
    "build",
    "inventory",
    "sniff",
    "hide",
    "guard_ahead",
    "reach",
    "stretch",
    "fly",
)
# the octopus's eight arms, clockwise from north
ARMS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
MAX_FLY = 5
MISS_LOOK = 5  # how far a missed grab looks for the item the animal was after
# where the item was, seen from the animal, in the order a miss is explained
SIDE_TURN = {"ahead": 0, "behind": 2, "left": -1, "right": 1}
SIDES = (("left", -1), ("ahead", 0), ("right", 1))
MAX_SAY = 200


class CrackError(Exception):
    """Raised when the ice ahead is too thin; a program can catch it with ``try``."""


CrackError.__module__ = "builtins"


class Timed(Awaitable):
    """A trick that takes time: ``await`` it and other tasks go on meanwhile."""

    KIND = "a trick that takes time"

    def __init__(self, duration: float, start: Callable[[], None], finish: Callable[[], Any]):
        self.duration = duration
        self.start = start
        self.finish = finish
        self.awaited = False
        self.label = "trick"

    def wait(self, runner: Any) -> Any:
        self.awaited = True
        self.start()
        yield ("sleep", self.duration)
        return self.finish()


@dataclass
class Pack:
    """Theme for one animal: names of the animal, its world, its actions and items.

    ``items`` maps a tile letter to the item's id, which is also what ``item_here()``
    returns to programs (``"banana"``), so programs read the same in every language.
    ``names`` holds what people see, per language: ``animal``, ``world`` and per tile
    noun forms ``{"one": ..., "few": ..., "many": ...}``.
    """

    id: str
    animal: str
    world: str
    actions: dict[str, str] = field(default_factory=dict)  # neutral -> themed name
    items: dict[str, str] = field(default_factory=dict)  # tile letter -> item id
    names: dict[str, dict[str, Any]] = field(default_factory=dict)  # lang -> names
    tricks: list[str] = field(default_factory=list)  # neutral names of the animal's own tricks
    emoji: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pack:
        return cls(
            id=data["id"],
            animal=data.get("animal", data["id"]),
            world=data.get("world", "world"),
            actions=dict(data.get("actions", {})),
            items=dict(data.get("items", {})),
            names=dict(data.get("names", {})),
            tricks=list(data.get("tricks", [])),
            emoji=data.get("emoji", ""),
        )

    def all_actions(self) -> tuple[str, ...]:
        return NEUTRAL_ACTIONS + tuple(trick for trick in TRICKS if trick in self.tricks)

    def action_name(self, neutral: str) -> str:
        return self.actions.get(neutral, neutral)

    def item_name(self, tile: str | None) -> str:
        """The item's id, as programs see it (``"banana"``)."""
        return self.items.get(tile or "", "item")

    def _names(self) -> dict[str, Any]:
        return self.names.get(current()) or self.names.get("en") or {}

    def animal_name(self) -> str:
        return self._names().get("animal", self.animal)

    def world_name(self) -> str:
        return self._names().get("world", self.world)

    def noun(self, tile: str | None, count: int = 1) -> str:
        """The item's name for people, in the right form for ``count``."""
        forms = self._names().get("items", {}).get(tile or "")
        if forms is None:
            name = self.item_name(tile)
            forms = {"one": name, "many": name if name.endswith("s") else name + "s"}
        return plural(count, forms)

    def nouns(self, tile: str | None) -> str:
        """Plural for "all the ...": ``bananas``, ``banány``."""
        return self.noun(tile, 3 if current() == "sk" else 2)

    def public(self) -> dict[str, Any]:
        """What clients need to draw and describe the pack, in the current language."""
        return {
            "id": self.id,
            "animal": self.animal,
            "world": self.world,
            "animalName": self.animal_name(),
            "worldName": self.world_name(),
            "actions": {name: self.action_name(name) for name in self.all_actions()},
            "tricks": list(self.tricks),
            "emoji": self.emoji,
            "items": self.items,
            "itemNames": {
                tile: {"one": self.noun(tile, 1), "many": self.nouns(tile)} for tile in self.items
            },
        }


DEFAULT_PACK = Pack("monkey", "monkey", "jungle", items={"B": "banana"})


class World:
    def __init__(
        self,
        width: int,
        height: int,
        walls: set[tuple[int, int]],
        items: dict[tuple[int, int], str],
        start: tuple[int, int, str],
        pack: Pack = DEFAULT_PACK,
    ) -> None:
        self.width = width
        self.height = height
        self.walls = walls
        self.items = items
        self.x, self.y, self.facing = start
        self.pack = pack
        self.terrain: dict[tuple[int, int], str] = {}
        self.collected: dict[str, int] = {}
        self.used: dict[str, int] = {}  # logs built into the dam, by tile letter
        self.built: dict[str, int] = {}  # by item id: {"oak": 2}
        self.hidden = False
        self.said: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.inputs: list[str] = []  # answers for input()
        self.files: dict[str, str] = {}  # the program's little disk for open()
        self.gil = True
        self.runner: Any = None  # set by the interpreter: tricks that take time use its clock
        self.timed: list[Timed] = []
        self.printed: list[str] = []  # the program's output, filled in after the run
        self.misses: list[dict[str, Any]] = []  # grab() where there was nothing to grab

    @classmethod
    def from_spec(cls, spec: dict[str, Any], pack: Pack = DEFAULT_PACK) -> World:
        """Build from a level's ``world`` object. Raises ``ValueError`` on bad specs."""
        tiles = spec.get("tiles")
        rows = tiles.split("\n") if isinstance(tiles, str) else tiles
        if not rows or not all(isinstance(r, str) and r for r in rows):
            raise ValueError("world.tiles must be a non-empty list of rows")
        width, height = len(rows[0]), len(rows)
        if any(len(row) != width for row in rows):
            raise ValueError("world.tiles rows must all have the same length")
        if "size" in spec and list(spec["size"]) != [width, height]:
            raise ValueError(f"world.size {spec['size']} does not match tiles {width}x{height}")
        walls: set[tuple[int, int]] = set()
        items: dict[tuple[int, int], str] = {}
        terrain: dict[tuple[int, int], str] = {}
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                if tile == WALL:
                    walls.add((x, y))
                elif tile.isalpha() and tile.isupper():
                    items[(x, y)] = tile
                elif tile in TERRAIN:
                    terrain[(x, y)] = tile
                elif tile != EMPTY:
                    raise ValueError(f"unknown tile {tile!r} at ({x}, {y})")
        for entry in spec.get("items", []):
            if not (isinstance(entry, list) and len(entry) == 3):
                raise ValueError('world.items entries must be [x, y, "C"]')
            x, y, tile = entry
            if not (0 <= x < width and 0 <= y < height) or (x, y) in walls:
                raise ValueError(f"world.items ({x}, {y}) is outside the grid or on a rock")
            if not (isinstance(tile, str) and len(tile) == 1 and tile.isupper()):
                raise ValueError(f"world.items tile {tile!r} must be a capital letter")
            items[(x, y)] = tile
        start = spec.get("start")
        if not (isinstance(start, list) and len(start) == 3 and start[2] in DIRECTIONS):
            raise ValueError('world.start must be [x, y, "north"|"east"|"south"|"west"]')
        x, y, facing = start
        if not (0 <= x < width and 0 <= y < height) or (x, y) in walls:
            raise ValueError(f"world.start ({x}, {y}) is outside the grid or on a wall")
        if terrain.get((x, y)) in (WATER, TREE):
            raise ValueError(f"world.start ({x}, {y}) is in water or a tree")
        world = cls(width, height, walls, items, (x, y, facing), pack)
        world.terrain = terrain
        inputs = spec.get("inputs", [])
        if not isinstance(inputs, list) or not all(isinstance(a, str) for a in inputs):
            raise ValueError("world.inputs must be a list of answers (text)")
        data = spec.get("data", {})
        if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            raise ValueError('world.data must map file names to text: {"scores.txt": "..."}')
        world.inputs = list(inputs)
        world.files = dict(data)
        world.gil = bool(spec.get("gil", True))
        return world

    @property
    def elapsed(self) -> float:
        """The simulated clock at the end of the run (tasks and threads)."""
        return float(self.runner.clock) if self.runner is not None else 0.0

    @property
    def forgot_await(self) -> bool:
        """A trick that takes time was started but never awaited, so it never happened."""
        return any(not timed.awaited for timed in self.timed)

    # --- actions (called by learner programs) ----------------------------------

    def actions(self) -> dict[str, Callable[..., Any]]:
        """Callable actions, sensors and tricks under the pack's names, plus ``CrackError``."""
        found: dict[str, Any] = {
            self.pack.action_name(n): getattr(self, n) for n in self.pack.all_actions()
        }
        if "slide" in self.pack.tricks or self.terrain_used(THIN_ICE):
            found["CrackError"] = CrackError
        return found

    def terrain_used(self, kind: str) -> bool:
        return kind in self.terrain.values()

    def step(self, n: int = 1) -> None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            name = self.pack.action_name("step")
            raise LearnerError(
                t("`{name}` needs a whole number of steps, like `{name}(3)`.", name=name),
                kind="type",
            )
        dx, dy = DIRECTIONS[self.facing]
        for _ in range(n):
            nx, ny = self.x + dx, self.y + dy
            if not self._inside(nx, ny):
                self._bump(
                    t(
                        "Bump! The {animal} reached the edge of the {world}.",
                        animal=self.pack.animal_name(),
                        world=self.pack.world_name(),
                    )
                )
            if (nx, ny) in self.walls:
                self._bump(
                    t("Bump! The {animal} walked into a wall.", animal=self.pack.animal_name())
                )
            self._enter(nx, ny)
            self._move_to(nx, ny)

    def _enter(self, x: int, y: int) -> None:
        """Checks for stepping onto terrain; raises before the animal moves."""
        animal = self.pack.animal_name()
        match self.terrain.get((x, y)):
            case "~":
                self._bump(t("Splash! The {animal} can't cross the water there.", animal=animal))
            case "t":
                self._bump(t("Bump! The {animal} walked into a tree.", animal=animal))
            case "-":
                self.events.append({"type": "crack", "at": [x, y]})
                raise LearnerError(
                    t("Crack! The ice ahead is too thin, so the {animal} stopped.", animal=animal),
                    kind="crack",
                    exception=CrackError("the ice ahead is too thin"),
                )
            case "o" if not self.hidden:
                self.events.append({"type": "bump", "at": [self.x, self.y], "facing": self.facing})
                raise LearnerError(
                    t(
                        "A guard saw the {animal}! Call `hide()` before stepping there.",
                        animal=animal,
                    ),
                    kind="bump",
                )

    def _move_to(self, x: int, y: int) -> None:
        self.events.append({"type": "move", "from": [self.x, self.y], "to": [x, y]})
        self.x, self.y = x, y
        self.hidden = False  # hiding lasts for one step

    def _inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def _bump(self, message: str) -> None:
        self.events.append({"type": "bump", "at": [self.x, self.y], "facing": self.facing})
        raise LearnerError(message, kind="bump")

    def turn_left(self) -> None:
        self._turn(-1)

    def turn_right(self) -> None:
        self._turn(1)

    def _turn(self, delta: int) -> None:
        self.facing = CLOCKWISE[(CLOCKWISE.index(self.facing) + delta) % 4]
        self.events.append({"type": "turn", "facing": self.facing})

    def grab(self) -> None:
        tile = self.items.pop((self.x, self.y), None)
        if tile is not None:
            self.collected[tile] = self.collected.get(tile, 0) + 1
            self.events.append({"type": "grab", "at": [self.x, self.y], "item": tile})
            return
        miss = self._nearest_item()
        self.misses.append(miss)
        self.events.append({"type": "grab", "at": [self.x, self.y], "item": None, **miss})

    def _nearest_item(self) -> dict[str, Any]:
        """Where the item a missed grab was after probably is: up in the tree ahead, or the
        closest one in a straight line ahead, behind, left or right (``near: none`` if no
        item is within a few squares)."""
        ahead = self._ahead()
        if self.terrain.get(ahead) == TREE and ahead in self.items:
            return {"near": "up", "distance": 1, "to": list(ahead), "target": self.items[ahead]}
        index = CLOCKWISE.index(self.facing)
        best: dict[str, Any] = {"near": "none"}
        for distance in range(1, MISS_LOOK + 1):
            for side, turn in SIDE_TURN.items():
                dx, dy = DIRECTIONS[CLOCKWISE[(index + turn) % 4]]
                spot = (self.x + dx * distance, self.y + dy * distance)
                if spot in self.items and self.terrain.get(spot) != TREE:
                    return {
                        "near": side,
                        "distance": distance,
                        "to": list(spot),
                        "target": self.items[spot],
                    }
        return best

    def say(self, text: Any = "") -> None:
        said = str(text)[:MAX_SAY]
        self.said.append(said)
        self.events.append({"type": "say", "text": said})

    # --- tricks: only animals whose pack lists them have these ---------------------------

    def _name(self, neutral: str) -> str:
        return self.pack.action_name(neutral)

    def swing(self) -> None:
        """Monkey: swing on a vine across one square of water or gap."""
        (gx, gy), (lx, ly) = self._ahead(), self._ahead(2)
        if self.terrain.get((gx, gy)) != WATER:
            raise LearnerError(
                t("There's no gap right ahead to `{name}()` across.", name=self._name("swing")),
                kind="bump",
            )
        if (
            not self._inside(lx, ly)
            or (lx, ly) in self.walls
            or self.terrain.get((lx, ly))
            in (
                WATER,
                TREE,
            )
        ):
            self._bump(
                t(
                    "The {animal} has nowhere to land on the other side.",
                    animal=self.pack.animal_name(),
                )
            )
        self.events.append({"type": "swing", "from": [self.x, self.y], "to": [lx, ly]})
        self.x, self.y = lx, ly
        self.hidden = False

    def climb(self) -> None:
        """Monkey: climb the tree right ahead and grab what grows at the top."""
        tree = self._ahead()
        if self.terrain.get(tree) != TREE:
            raise LearnerError(
                t("There's no tree right ahead to `{name}()`.", name=self._name("climb")),
                kind="bump",
            )
        tile = self.items.pop(tree, None)
        if tile is not None:
            self.collected[tile] = self.collected.get(tile, 0) + 1
        self.events.append({"type": "climb", "at": list(tree), "item": tile})

    def slide(self) -> int:
        """Penguin: slide on the belly until something is in the way; returns the squares slid.

        Thin ice ahead stops the slide with a ``CrackError``.
        """
        slid = 0
        while True:
            x, y = self._ahead()
            blocked = not self._inside(x, y) or (x, y) in self.walls
            if blocked or self.terrain.get((x, y)) in (WATER, TREE):
                return slid
            self._enter(x, y)
            self.events.append(
                {"type": "move", "from": [self.x, self.y], "to": [x, y], "slide": True}
            )
            self.x, self.y = x, y
            slid += 1

    def inventory(self) -> dict[str, int]:
        """Beaver: the logs it carries, like ``{"oak": 2, "pine": 1}``."""
        held = {}
        for tile, count in sorted(self.collected.items()):
            left = count - self.used.get(tile, 0)
            if left > 0:
                held[self.pack.item_name(tile)] = left
        return self._sense("inventory", held)

    def build(self, log: Any = None) -> None:
        """Beaver: lay one log (``"oak"``) into the water ahead, making a bridge."""
        by_name = {self.pack.item_name(tile): tile for tile in self.collected}
        tile = by_name.get(str(log)) if isinstance(log, str) else None
        if tile is None or self.collected.get(tile, 0) - self.used.get(tile, 0) <= 0:
            have = ", ".join(f'"{name}"' for name in self.inventory()) or t("none")
            raise LearnerError(
                t(
                    "The {animal} has no {log} log to build with. Logs it carries: {have}.",
                    animal=self.pack.animal_name(),
                    log=repr(log),
                    have=have,
                ),
                kind="type",
                exception=ValueError(f"no {log!r} log"),
            )
        ahead = self._ahead()
        if self.terrain.get(ahead) != WATER:
            raise LearnerError(
                t("`{name}()` needs water right ahead.", name=self._name("build")),
                kind="bump",
            )
        self.used[tile] = self.used.get(tile, 0) + 1
        name = self.pack.item_name(tile)
        self.built[name] = self.built.get(name, 0) + 1
        self.terrain[ahead] = BRIDGE
        self.events.append({"type": "build", "at": list(ahead), "item": tile})

    def sniff(self) -> list[str]:
        """Fox: the open ways from here, among ``"left"``, ``"ahead"``, ``"right"``."""
        index = CLOCKWISE.index(self.facing)
        open_ways = []
        for side, turn in SIDES:
            dx, dy = DIRECTIONS[CLOCKWISE[(index + turn) % 4]]
            x, y = self.x + dx, self.y + dy
            if (
                self._inside(x, y)
                and (x, y) not in self.walls
                and self.terrain.get((x, y)) not in (WATER, TREE)
            ):
                open_ways.append(side)
        return self._sense("sniff", open_ways)

    def hide(self) -> None:
        """Fox: hide, so the next step onto a watched spot goes unseen."""
        self.hidden = True
        self.events.append({"type": "hide", "at": [self.x, self.y]})

    def guard_ahead(self) -> bool:
        """Fox: True when a guard watches the square ahead."""
        return self._sense("guard_ahead", self.terrain.get(self._ahead()) == WATCHED)

    def _arm(self, arm: Any) -> tuple[list[int], tuple[int, int] | None, int]:
        """Where arm number ``arm`` reaches: (tip, square with an item or None, squares)."""
        name = self._name("reach")
        if isinstance(arm, bool) or not isinstance(arm, int) or not 0 <= arm < len(ARMS):
            raise LearnerError(
                t("The octopus has arms 0 to 7: `{name}(3)`, not {arm}.", name=name, arm=repr(arm)),
                kind="type",
                exception=ValueError(f"no arm {arm!r}"),
            )
        dx, dy = ARMS[arm]
        x, y, squares = self.x, self.y, 0
        while True:
            nx, ny = x + dx, y + dy
            if not self._inside(nx, ny) or (nx, ny) in self.walls:
                return [x, y], None, squares
            x, y, squares = nx, ny, squares + 1
            if (x, y) in self.items:
                return [x, y], (x, y), squares

    def _reach_parts(self, arm: Any) -> tuple[float, Callable[[], None], Callable[[], str]]:
        tip, target, squares = self._arm(arm)
        duration = max(2 * squares, 1)  # out and back, one tick per square each way

        def start() -> None:
            tile = self.items.get(target) if target else None
            self.events.append(
                {"type": "reach", "arm": arm, "to": tip, "item": tile, "duration": duration}
            )

        def finish() -> str:
            tile = self.items.pop(target, None) if target else None
            if tile is not None:
                self.collected[tile] = self.collected.get(tile, 0) + 1
            self.events.append({"type": "grab", "at": tip, "item": tile, "arm": arm})
            return self.pack.item_name(tile) if tile else ""

        return duration, start, finish

    def reach(self, arm: Any = 0) -> Timed:
        """Octopus: stretch arm ``arm`` (0-7, clockwise from north) to the first thing in
        that direction and bring it back. ``await`` it; meanwhile other arms can move."""
        duration, start, finish = self._reach_parts(arm)
        timed = Timed(duration, start, finish)
        timed.label = f"arm {arm}"
        self.timed.append(timed)
        return timed

    def stretch(self, arm: Any = 0) -> str:
        """Octopus: like ``reach``, for threads: the thread waits while the arm moves."""
        duration, start, finish = self._reach_parts(arm)
        start()
        found = finish()
        runner = self.runner
        if runner is not None and runner.threads is not None and runner.threads.running:
            runner.pending = ("sleep", duration)
        elif runner is not None:
            runner.clock += duration
        return found

    def fly(self, n: int = 1) -> None:
        """Bee: fly ``n`` squares ahead, over rocks, water and trees; land on open ground."""
        name = self._name("fly")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_FLY:
            raise LearnerError(
                t(
                    "`{name}` needs a whole number from 1 to {most}, like `{name}(2)`.",
                    name=name,
                    most=MAX_FLY,
                ),
                kind="type",
            )
        x, y = self._ahead(n)
        if not self._inside(x, y):
            self._bump(
                t(
                    "Bump! The {animal} reached the edge of the {world}.",
                    animal=self.pack.animal_name(),
                    world=self.pack.world_name(),
                )
            )
        if (x, y) in self.walls or self.terrain.get((x, y)) in (WATER, TREE):
            self._bump(t("The {animal} has nowhere to land there.", animal=self.pack.animal_name()))
        self.events.append({"type": "fly", "from": [self.x, self.y], "to": [x, y]})
        self.x, self.y = x, y
        self.hidden = False

    # --- sensors -------------------------------------------------------------------

    def _ahead(self, distance: int = 1) -> tuple[int, int]:
        dx, dy = DIRECTIONS[self.facing]
        return self.x + dx * distance, self.y + dy * distance

    def _sense(self, what: str, result: Any) -> Any:
        self.events.append({"type": "sense", "what": what, "result": result})
        return result

    def is_blocked(self) -> bool:
        """True when a wall or the edge of the world is right ahead."""
        x, y = self._ahead()
        blocked = not self._inside(x, y) or (x, y) in self.walls
        return self._sense("is_blocked", blocked or self.terrain.get((x, y)) in (WATER, TREE))

    def item_here(self) -> str:
        """The item on this square (``"banana"``), or ``""`` when there is none."""
        tile = self.items.get((self.x, self.y))
        return self._sense("item_here", self.pack.item_name(tile) if tile else "")

    def item_ahead(self) -> str:
        """The item on the square ahead, or ``""``."""
        tile = self.items.get(self._ahead())
        return self._sense("item_ahead", self.pack.item_name(tile) if tile else "")

    # --- reading the world -------------------------------------------------------

    def drain_events(self) -> list[dict[str, Any]]:
        events, self.events = self.events, []
        return events

    def remaining(self, item: str | None = None) -> int:
        return sum(1 for tile in self.items.values() if item is None or tile == item)

    def render(self) -> str:
        rows = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                if (x, y) == (self.x, self.y):
                    row.append(ARROWS[self.facing])
                elif (x, y) in self.walls:
                    row.append(WALL)
                else:
                    row.append(self.items.get((x, y), self.terrain.get((x, y), EMPTY)))
            rows.append("".join(row))
        return "\n".join(rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": [self.width, self.height],
            "position": [self.x, self.y],
            "facing": self.facing,
            "items": [[x, y, tile] for (x, y), tile in sorted(self.items.items())],
            "collected": dict(self.collected),
            "said": list(self.said),
            "terrain": [[x, y, kind] for (x, y), kind in sorted(self.terrain.items())],
            "built": dict(self.built),
            "files": dict(self.files),
            "elapsed": self.elapsed,
        }
