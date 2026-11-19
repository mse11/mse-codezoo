"""Grid world: the animal, walls and items, and the neutral actions that change them.

Actions append events (``move``, ``turn``, ``grab``, ``say``, ``bump``) that clients
animate. Animal packs rename actions and items; the world itself stays neutral.
Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mse_codezoo.interpreter import LearnerError

DIRECTIONS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
CLOCKWISE = ["north", "east", "south", "west"]
ARROWS = {"north": "^", "east": ">", "south": "v", "west": "<"}
EMPTY = "."
WALL = "#"
NEUTRAL_ACTIONS = ("step", "turn_left", "turn_right", "grab", "say")
MAX_SAY = 200


@dataclass
class Pack:
    """Theme for one animal: names of the animal, its world, its actions and items."""

    id: str
    animal: str
    world: str
    actions: dict[str, str] = field(default_factory=dict)  # neutral -> themed name
    items: dict[str, str] = field(default_factory=dict)  # tile letter -> noun

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pack:
        return cls(
            id=data["id"],
            animal=data.get("animal", data["id"]),
            world=data.get("world", "world"),
            actions=dict(data.get("actions", {})),
            items=dict(data.get("items", {})),
        )

    def action_name(self, neutral: str) -> str:
        return self.actions.get(neutral, neutral)

    def item_name(self, tile: str) -> str:
        return self.items.get(tile, "item")


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
        self.collected: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []

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
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                if tile == WALL:
                    walls.add((x, y))
                elif tile.isalpha() and tile.isupper():
                    items[(x, y)] = tile
                elif tile != EMPTY:
                    raise ValueError(f"unknown tile {tile!r} at ({x}, {y})")
        start = spec.get("start")
        if not (isinstance(start, list) and len(start) == 3 and start[2] in DIRECTIONS):
            raise ValueError('world.start must be [x, y, "north"|"east"|"south"|"west"]')
        x, y, facing = start
        if not (0 <= x < width and 0 <= y < height) or (x, y) in walls:
            raise ValueError(f"world.start ({x}, {y}) is outside the grid or on a wall")
        return cls(width, height, walls, items, (x, y, facing), pack)

    # --- actions (called by learner programs) ----------------------------------

    def actions(self) -> dict[str, Callable[..., Any]]:
        """Callable actions under the pack's names."""
        return {self.pack.action_name(n): getattr(self, n) for n in NEUTRAL_ACTIONS}

    def step(self, n: int = 1) -> None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            name = self.pack.action_name("step")
            raise LearnerError(f"`{name}` needs a whole number of steps, like `{name}(3)`.")
        dx, dy = DIRECTIONS[self.facing]
        for _ in range(n):
            nx, ny = self.x + dx, self.y + dy
            if not (0 <= nx < self.width and 0 <= ny < self.height):
                self._bump(f"reached the edge of the {self.pack.world}")
            if (nx, ny) in self.walls:
                self._bump("walked into a wall")
            self.events.append({"type": "move", "from": [self.x, self.y], "to": [nx, ny]})
            self.x, self.y = nx, ny

    def _bump(self, what: str) -> None:
        self.events.append({"type": "bump", "at": [self.x, self.y], "facing": self.facing})
        raise LearnerError(f"Bump! The {self.pack.animal} {what}.")

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

    def say(self, text: Any = "") -> None:
        self.events.append({"type": "say", "text": str(text)[:MAX_SAY]})

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
                    row.append(self.items.get((x, y), EMPTY))
            rows.append("".join(row))
        return "\n".join(rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": [self.width, self.height],
            "position": [self.x, self.y],
            "facing": self.facing,
            "items": [[x, y, tile] for (x, y), tile in sorted(self.items.items())],
            "collected": dict(self.collected),
        }
