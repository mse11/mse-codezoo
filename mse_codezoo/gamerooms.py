"""Game mode G3: several children play one world together, over the classroom hub.

A *room* holds one game for up to ``MAX_PLAYERS`` animals. The hub (or ``codezoo serve``)
runs the game; children's devices only send keys and draw what comes back:

- **Input lockstep on the deterministic engine.** Keys pressed between two ticks wait in
  the room; each tick takes every player's keys in the order the players joined and runs
  the handlers once. ``MultiGame.inputs`` records them, so ``replay()`` gives the same game
  again, tick by tick (the desync test).
- **Push updates.** Every tick goes to every device as a server-sent event
  (``GET /api/room/events``); each message has the whole state, so a device that missed
  one just draws the next.
- **No chat.** Children can send only an emoji from ``REACTIONS``.

How a program sees several animals: before running a handler for one player, the game
puts that player's animal into the world, so ``go()``, ``grab()``, ``where()`` and
``on_item`` / ``on_touch`` act on it; ``player()`` says which one (1, 2...) and
``animals()`` where all of them are. ``on_tick`` and the critters run once per tick with
player 1 in the world. The score is the team's. With the ``caught`` rule, a caught
animal goes back to its start instead of ending everyone's game.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import queue
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from mse_codezoo import gamemode
from mse_codezoo.gamemode import (
    PLAYING,
    TICK_BUDGET,
    TICK_MS,
    Game,
    GameSpec,
    PlayerState,
    clean_keys,
)
from mse_codezoo.i18n import t
from mse_codezoo.levels import animal_names

MAX_PLAYERS = 4
MAX_ROOMS = 12
REACTIONS = ("👍", "😂", "😮", "🎉", "❤️", "😅")
IDLE_SECONDS = 600  # a room nobody touched for 10 minutes closes
MAX_QUEUED = 8  # keys a player can queue between ticks
LOBBY, RUNNING, ENDED = "lobby", "playing", "ended"


class RoomError(ValueError):
    """Something a child tried that a room can't do (full, already started...)."""


# --- the engine: several animals in one world ----------------------------------------


class MultiGame(Game):
    """A ``Game`` with one animal per player. ``tick_all({1: ["up"], 2: []})``."""

    def __init__(
        self,
        spec: GameSpec,
        source: str,
        players: list[tuple[str, str]],
        *,
        seed: int = 0,
        version: tuple[int, int] | None = None,
        budget: int = TICK_BUDGET,
    ) -> None:
        super().__init__(spec, source, seed=seed, version=version, budget=budget)
        starts = start_squares(self, len(players))
        self.players = [
            PlayerState(n, name, x, y, f, (x, y, f), look if look in animal_names() else "")
            for n, ((name, look), (x, y, f)) in enumerate(zip(players, starts, strict=True), 1)
        ]
        self.current = self.players[0]
        self.multi_inputs: list[dict[str, list[str]]] = []
        # players who joined a game already running: {"tick": n, "name", "look"}, so a
        # replay adds them before the same tick (lockstep stays exact)
        self.joins: list[dict[str, Any]] = []

    def add_player(self, name: str, look: str) -> PlayerState:
        """A late joiner's animal: on the free square nearest the world's start."""
        self.keep()
        world, first = self.world, self.players[0]
        here = (world.x, world.y, world.facing)
        world.x, world.y, world.facing = first.start
        squares = start_squares(self, len(self.players) + 1)
        world.x, world.y, world.facing = here
        taken = {(p.x, p.y) for p in self.players}
        x, y, facing = next((s for s in squares if (s[0], s[1]) not in taken), squares[-1])
        player = PlayerState(
            len(self.players) + 1,
            name,
            x,
            y,
            facing,
            (x, y, facing),
            look if look in animal_names() else "",
        )
        self.players.append(player)
        self.joins.append({"tick": len(self.multi_inputs), "name": name, "look": look})
        return player

    # --- whose animal is in the world ----------------------------------------------

    def use(self, player: PlayerState) -> None:
        self.keep()
        world = self.world
        world.x, world.y, world.facing, world.hidden = (
            player.x,
            player.y,
            player.facing,
            player.hidden,
        )
        self.current = player

    def keep(self) -> None:
        world, player = self.world, self.current
        player.x, player.y, player.facing, player.hidden = (
            world.x,
            world.y,
            world.facing,
            world.hidden,
        )

    def player(self) -> int:
        return self.current.number

    def animals(self) -> list[tuple[int, int]]:
        self.keep()
        return [(p.x, p.y) for p in self.players]

    def animal_squares(self) -> set[tuple[int, int]]:
        self.keep()
        return {(p.x, p.y) for p in self.players}

    def caught(self) -> None:
        """A caught animal goes back to its start; the others play on."""
        player = self.current
        player.caught += 1
        x, y, facing = player.start
        world = self.world
        world.events.append({"type": "move", "from": [world.x, world.y], "to": [x, y]})
        world.x, world.y, world.facing = x, y, facing
        self.note(t("A critter caught {name}! Back to the start.", name=player.name))

    # --- a tick for everyone ---------------------------------------------------------

    def start(self) -> gamemode.TickResult:
        self.use(self.players[0])
        return super().start()

    def tick(self, keys: list[str] | None = None) -> gamemode.TickResult:
        return self.tick_all({1: clean_keys(keys)})

    def tick_all(self, keys: dict[int, list[str]]) -> gamemode.TickResult:
        if self.status != PLAYING:
            return self._finish_tick()
        pressed = {p.number: clean_keys(keys.get(p.number)) for p in self.players}
        self.multi_inputs.append({str(n): k for n, k in pressed.items()})
        self.inputs.append(pressed[1])
        # every animal's keys share one budget, a little bigger for more players
        self._begin_tick(self.budget * (1 + len(self.players)) // 2)
        starts = {}
        for player in self.players:
            self.use(player)
            starts[player.number] = (player.x, player.y)
            self._keys(pressed[player.number])
        self.use(self.players[0])
        self._tick_handlers()
        for player in self.players:
            if self.status != PLAYING:
                break
            self.use(player)
            self._arrivals(starts[player.number])
            player.touching = self._touches(player.touching)
        self.use(self.players[0])
        self._rules()
        return self._finish_tick()

    def state(self) -> dict[str, Any]:
        self.keep()
        data = super().state()
        first = self.players[0]
        data["animal"] = {"at": [first.x, first.y], "facing": first.facing}
        data["players"] = [
            {
                "number": p.number,
                "name": p.name,
                "look": p.look,
                "at": [p.x, p.y],
                "facing": p.facing,
                "caught": p.caught,
            }
            for p in self.players
        ]
        return data


def start_squares(game: Game, count: int) -> list[tuple[int, int, str]]:
    """Where the animals start: the world's start, then the nearest free open squares."""
    world = game.world
    start = (world.x, world.y)
    taken = {tuple(o["at"]) for o in game.spec.objects()}
    found = [(world.x, world.y, world.facing)]
    todo, seen = [start], {start}
    for square in todo:
        for _, nx, ny in gamemode._neighbours(*square):
            if (nx, ny) in seen or not gamemode._walkable(game, nx, ny):
                continue
            seen.add((nx, ny))
            todo.append((nx, ny))
            if len(found) < count and (nx, ny) not in taken and (nx, ny) not in world.items:
                found.append((nx, ny, world.facing))
    while len(found) < count:  # a tiny world: animals share a square
        found.append(found[-1])
    return found


def replay(
    spec: GameSpec,
    source: str,
    players: list[tuple[str, str]],
    inputs: list[dict[str, list[str]]],
    *,
    seed: int = 0,
    joins: list[dict[str, Any]] | None = None,
) -> MultiGame:
    """The same game again from its recorded keys (what lockstep promises), with the
    players who joined late added before the same ticks."""
    game = MultiGame(spec, source, players, seed=seed)
    game.start()
    waiting = sorted(joins or [], key=lambda join: join["tick"])
    for index, keys in enumerate(inputs):
        while waiting and waiting[0]["tick"] <= index:
            join = waiting.pop(0)
            game.add_player(join["name"], join["look"])
        game.tick_all({int(n): k for n, k in keys.items()})
    return game


def checksum(state: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:12]


# --- a room on the hub -----------------------------------------------------------------


@dataclass
class Seat:
    token: str
    profile: str
    name: str
    picture: str
    look: str
    keys: list[str] = field(default_factory=list)


class Room:
    """One shared world: a lobby, then a game ticking by itself, then the end."""

    def __init__(
        self,
        room_id: str,
        spec: GameSpec,
        source: str,
        title: str,
        *,
        auto: bool = True,
        paused: Any = None,
    ) -> None:
        self.id = room_id
        self.spec = spec
        self.source = source
        self.title = title
        self.seats: list[Seat] = []
        self.status = LOBBY
        self.game: MultiGame | None = None
        self.auto = auto  # False in tests: call advance() instead of a ticking thread
        self.paused = paused or (lambda: False)  # the hub's "eyes on the teacher"
        self.lock = threading.RLock()
        self.listeners: list[queue.Queue[dict[str, Any] | None]] = []
        self.touched = time.monotonic()
        self.checksums: list[str] = []
        self.created = time.time()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- seats -------------------------------------------------------------------

    def join(self, profile: str, name: str, picture: str, look: str) -> Seat:
        with self.lock:
            self.touched = time.monotonic()
            for seat in self.seats:
                if seat.profile == profile:
                    seat.look = look or seat.look
                    return seat
            if self.status == ENDED:
                raise RoomError(t("That world has closed. Open a new one!"))
            if len(self.seats) >= MAX_PLAYERS:
                raise RoomError(
                    t("This world is full: {count} animals already.", count=MAX_PLAYERS)
                )
            seat = Seat(secrets.token_urlsafe(12), profile, name, picture, look)
            self.seats.append(seat)
            if self.status == RUNNING and self.game is not None:
                # joining a game that has started: a new animal near the start
                self.game.add_player(name, look)
            self.broadcast({"type": "room", "room": self.public()})
            return seat

    def seat(self, token: Any) -> Seat:
        for seat in self.seats:
            if isinstance(token, str) and secrets.compare_digest(seat.token, token):
                return seat
        raise RoomError(t("You are not in this world. Join it first."))

    def number(self, seat: Seat) -> int:
        return self.seats.index(seat) + 1

    def leave(self, token: Any) -> None:
        with self.lock:
            seat = self.seat(token)
            self.touched = time.monotonic()
            if self.status == LOBBY:
                self.seats.remove(seat)
                if not self.seats:
                    self.end(t("Everyone left."))
                    return
            else:
                seat.keys.clear()  # the animal stays and just stops moving
            self.broadcast({"type": "room", "room": self.public()})

    # --- playing -----------------------------------------------------------------

    def start(self, token: Any, *, version: tuple[int, int] | None = None) -> dict[str, Any]:
        with self.lock:
            seat = self.seat(token)
            if self.number(seat) != 1:
                raise RoomError(t("The one who opened the world starts the game."))
            if self.status != LOBBY:
                raise RoomError(t("This game has started already. Wait for the next one!"))
            players = [(s.name, s.look) for s in self.seats]
            self.game = MultiGame(self.spec, self.source, players, version=version)
            result = self.game.start()
            self.status = RUNNING
            self.broadcast({"type": "room", "room": self.public()})
            message = self._message("start", result)
            self.broadcast(message)
            if self.game.status != PLAYING:
                self.end(self.game.message)
            elif self.auto:
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name=f"room-{self.id}"
                )
                self._thread.start()
            return message

    def keys(self, token: Any, keys: Any) -> None:
        with self.lock:
            seat = self.seat(token)
            self.touched = time.monotonic()
            room = MAX_QUEUED - len(seat.keys)
            seat.keys.extend(clean_keys(keys if isinstance(keys, list) else [])[: max(0, room)])

    def react(self, token: Any, emoji: Any) -> None:
        with self.lock:
            seat = self.seat(token)
            if emoji not in REACTIONS:
                raise RoomError(t("Pick one of the emoji."))
            self.touched = time.monotonic()
            self.broadcast({"type": "react", "player": self.number(seat), "emoji": emoji})

    def advance(self) -> dict[str, Any] | None:
        """One tick: every player's waiting keys (a few each), in joining order."""
        with self.lock:
            game = self.game
            if game is None or self.status != RUNNING or self.paused():
                return None
            keys = {}
            for number, seat in enumerate(self.seats, 1):
                keys[number] = seat.keys[: gamemode.MAX_KEYS]
                del seat.keys[: gamemode.MAX_KEYS]
            result = game.tick_all(keys)
            message = self._message("tick", result)
            self.broadcast(message)
            if game.status != PLAYING:
                self.end(game.message)
            return message

    def _run(self) -> None:
        next_tick = time.monotonic()
        while not self._stop.is_set():
            next_tick += TICK_MS / 1000
            self.advance()
            if self.status != RUNNING:
                return
            self._stop.wait(max(0.0, next_tick - time.monotonic()))

    def end(self, message: str = "") -> None:
        with self.lock:
            if self.status == ENDED:
                return
            self.status = ENDED
            self._stop.set()
            self.broadcast({"type": "end", "message": message, "room": self.public()})
            for listener in self.listeners:
                listener.put(None)

    def _message(self, kind: str, result: gamemode.TickResult) -> dict[str, Any]:
        assert self.game is not None
        data = self.game.to_json(result)
        data.pop("features", None)
        state = data["state"]
        self.checksums.append(checksum(state))
        return {"type": kind, "sum": self.checksums[-1], **data}

    # --- who is watching ---------------------------------------------------------

    def listen(self) -> queue.Queue[dict[str, Any] | None]:
        """A device's queue of messages; the first says where everything is now."""
        with self.lock:
            listener: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=64)
            listener.put({"type": "room", "room": self.public()})
            if self.game is not None:
                listener.put(
                    {
                        "type": "tick",
                        "state": self.game.state(),
                        "events": [],
                        "lines": [],
                        "output": [],
                        "notes": [],
                        "error": self.game.error_json(),
                    }
                )
            if self.status == ENDED:
                listener.put(
                    {
                        "type": "end",
                        "message": self.game.message if self.game else "",
                        "room": self.public(),
                    }
                )
                listener.put(None)
            self.listeners.append(listener)
            return listener

    def unlisten(self, listener: queue.Queue[dict[str, Any] | None]) -> None:
        with self.lock:
            if listener in self.listeners:
                self.listeners.remove(listener)

    def broadcast(self, message: dict[str, Any]) -> None:
        for listener in list(self.listeners):
            try:
                listener.put_nowait(message)
            except queue.Full:  # a device that stopped reading: it catches up on reconnect
                self.listeners.remove(listener)
                try:
                    listener.get_nowait()
                    listener.put_nowait(None)
                except (queue.Empty, queue.Full):
                    pass

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "game": self.spec.id,
            "status": self.status,
            "max": MAX_PLAYERS,
            "players": [
                {"number": n, "name": s.name, "picture": s.picture, "look": s.look}
                for n, s in enumerate(self.seats, 1)
            ],
            # a child can join until the world is full, also while the game runs
            "joinable": self.status != ENDED and len(self.seats) < MAX_PLAYERS,
        }

    def teacher(self) -> dict[str, Any]:
        """What the teacher's screen shows about a room: the game, who plays, how far."""
        data = self.public()
        game = self.game
        data["tick"] = game.tick_count if game else 0
        data["score"] = game.score.value if game else 0
        data["minutes"] = round((time.time() - self.created) / 60)
        return data


class Rooms:
    """The rooms of one server (a classroom hub), newest last."""

    def __init__(self, limit: int = MAX_ROOMS, *, auto: bool = True) -> None:
        self.limit = limit
        self.auto = auto
        self.paused: Any = lambda: False
        self._rooms: OrderedDict[str, Room] = OrderedDict()
        self._lock = threading.Lock()

    def open(self, spec: GameSpec, source: str, title: str) -> Room:
        with self._lock:
            self._tidy()
            if len(self._rooms) >= self.limit:
                raise RoomError(t("There are many worlds open already. Join one of them!"))
            room = Room(
                f"r{secrets.token_hex(4)}",
                spec,
                source,
                title,
                auto=self.auto,
                paused=lambda: self.paused(),
            )
            self._rooms[room.id] = room
            return room

    def get(self, room_id: Any) -> Room:
        with self._lock:
            room = self._rooms.get(room_id) if isinstance(room_id, str) else None
        if room is None:
            raise RoomError(t("That world has closed. Open a new one!"))
        return room

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._tidy()
            return [room.public() for room in self._rooms.values() if room.status != ENDED]

    def teacher_list(self) -> list[dict[str, Any]]:
        """Every open room for the teacher's screen (newest last)."""
        with self._lock:
            self._tidy()
            rooms = [room for room in self._rooms.values() if room.status != ENDED]
        return [room.teacher() for room in rooms]

    def close(self, room_id: Any, message: str = "") -> None:
        """The teacher closes one room; the children in it see why."""
        room = self.get(room_id)
        room.end(message)
        with self._lock:
            self._rooms.pop(room.id, None)

    def close_all(self, message: str = "") -> None:
        with self._lock:
            rooms = list(self._rooms.values())
            self._rooms.clear()
        for room in rooms:
            room.end(message)

    def _tidy(self) -> None:
        now = time.monotonic()
        for room_id, room in list(self._rooms.items()):
            if room.status == ENDED and not room.listeners:
                del self._rooms[room_id]
            elif now - room.touched > IDLE_SECONDS:
                room.end(t("Nobody played for a while, so the world closed."))
                del self._rooms[room_id]


class EventStream:
    """What ``GET /api/room/events`` answers: the HTTP server streams the room's messages
    as server-sent events until the room ends or the device goes away."""

    def __init__(self, room: Room) -> None:
        self.room = room
        self.listener = room.listen()

    def messages(self, keepalive: float = 15.0) -> Any:
        """Yields a message (a dict), or None when it is time for a keep-alive."""
        try:
            while True:
                try:
                    message = self.listener.get(timeout=keepalive)
                except queue.Empty:
                    yield None
                    continue
                if message is None:
                    return
                yield message
        finally:
            self.room.unlisten(self.listener)


ROOMS = Rooms()
