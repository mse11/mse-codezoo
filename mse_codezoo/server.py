"""Local web server behind ``codezoo serve``: static web client plus a small JSON API.

The browser edits IR JSON and asks the engine to parse, print and run; it never parses
Python itself. Binds to localhost by default. Standard library only.

API (all JSON):
    GET  /api/levels             level list
    GET  /api/levels/<id>        one level, ready to draw
    POST /api/parse   {source}   -> {ok, diagnostics, program, positions}
    POST /api/print   {program}  -> {text, sourceMap}
    POST /api/run     {level, source, animal?, variant?, profile?} -> run (as
                      `codezoo run --json`); with a profile, the result is saved to that
                      player's progress

Every request may pick a language with ``?lang=sk`` (or ``"lang"`` in a POST body);
otherwise the browser's ``Accept-Language`` decides. Titles, hints and messages follow it.
    GET  /api/profiles                 players, pictures, public grown-up settings
    POST /api/profiles {name, picture} -> new player
    POST /api/profiles/<id>/picture {picture} -> the player with a new picture
    GET  /api/profiles/<id>/progress   stars per level, today's minutes and limit
    POST /api/profiles/<id>/time {seconds} -> today's minutes and limit
    POST /api/parent/<action> {pin?, ...}  check | settings | report | export | remove |
                                       import {data} (a file from `profile export`) |
                                       cub {profile, on} (Cub mode, phase 7)

Phase 3:
    GET  /api/animals                  every animal pack, ready to draw
    POST /api/run  also takes {modules?: {"tricks": "..."}, save?: true,
                   levelData?: {...}} (a level from the editor); with a profile it answers
                   new stickers and a practice suggestion too
    POST /api/story {run}              -> {html}: a printable storybook of a saved run
    GET  /cards.html?animal=monkey     printable unplugged cards
    POST /api/profiles/<id>/unlock {code}      -> {card, sticker, new}
    GET  /api/profiles/<id>/habitat            stickers, their places, outfits
    POST /api/profiles/<id>/habitat {placed?, outfit?}
    POST /api/levels/check {level, solution}   -> {errors}: the editor's "Test" button

Phase 4:
    every request may pick the Python release with ``?python=3.12`` (or ``"python"`` in a
    POST body); levels list their ``minPython`` and say when they are ``locked`` here.
    GET  /api/info                     engine version, Python releases this engine reads
    POST /api/levels/preview {level, animal?}  a level from the editor (or a share link),
                                               checked, then ready to draw
    All routes go through ``dispatch()``, which the offline browser build calls directly
    inside Pyodide instead of over HTTP.

Phase 5: ``codezoo class serve`` gives the server a classroom hub (``hub.Hub``), which
checks the class code or the teacher's key and adds ``/api/class/*`` and ``/api/teacher/*``
before passing the usual routes on to ``dispatch()``.

Game mode (phase 8, see ``gamemode.py``): a running game stays in memory between ticks
(``gamemode.SESSIONS``), on the server or in the offline build's web worker.
    GET  /api/games                    games to play, ready to list
    GET  /api/games/<id>               one game, ready to draw (starter program, help)
    POST /api/game/start {game | gameData, source, animal?, seed?} -> {session, state, ...}
    POST /api/game/tick  {session, keys: ["left", ...]}            -> {state, events, lines}
    POST /api/game/stop  {session}
    POST /api/game/test  {game | gameData, source, animal?, games?} -> the playtest bot's report
    POST /api/game/preview {gameData, animal?}  a game from the world editor or a share link

Playing together (G3, see ``gamerooms.py``): rooms where several animals share one world.
The game runs here; devices send keys and get every tick pushed as server-sent events.
    GET  /api/rooms                                   open worlds to join
    POST /api/room/open  {game | gameData, source, profile?, look?} -> {room, seat, number}
    POST /api/room/join  {room, profile?, look?}       -> {room, seat, number}
    POST /api/room/start {room, seat}                  only the one who opened it
    POST /api/room/keys  {room, seat, keys}
    POST /api/room/react {room, seat, emoji}           an emoji from a fixed list, no chat
    POST /api/room/leave {room, seat}
    GET  /api/room/events?room=                        text/event-stream, one message a tick
The offline build has no rooms: playing together needs a server on the local network.
"""

from __future__ import annotations

import json
import mimetypes
import re
import secrets
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from mse_codezoo import __version__, gamemode, gamerooms, ir, pilot, versions
from mse_codezoo.cards import card_for_code, card_public, cards_html
from mse_codezoo.game import (
    attempt_from_run,
    level_to_json,
    lock_reason,
    run_level,
    run_to_json,
    solution_errors,
)
from mse_codezoo.i18n import from_accept_language, normalize, t, use_lang
from mse_codezoo.lang_python import parse, print_program
from mse_codezoo.levels import (
    Level,
    LevelError,
    animal_names,
    find_level,
    level_files,
    load_level,
    load_pack,
    validate_level_data,
)
from mse_codezoo.profiles import PinError, ProfileError, ProfileStore
from mse_codezoo.runs import RunFileError, make_run
from mse_codezoo.story import storybook_html

WEB_DIR = Path(__file__).parent / "web"
MAX_BODY = 2 * 1024 * 1024  # a saved run for the storybook can be large
DRAIN_LIMIT = 16 * 1024 * 1024  # larger bodies are not read; the connection is closed
DEFAULT_PORT = 8765
PROGRESS_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/progress$")
TIME_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/time$")
PARENT_PATH = re.compile(r"^/api/parent/(?P<action>[a-z-]+)$")
UNLOCK_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/unlock$")
HABITAT_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/habitat$")
PILOT_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/pilot$")
PICTURE_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/picture$")
CHECK_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/check$")
GAME_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
ROOM_ACTION = re.compile(r"^(open|join|start|keys|react|leave)$")
QUESTIONS_PATH = re.compile(r"^/api/checks/(?P<module>[a-z0-9-]{1,40})$")
MAX_MODULES = 5


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _python(value: Any) -> tuple[int, int] | None:
    try:
        return versions.parse_version(value if isinstance(value, str) else None)
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from None


def api_info() -> dict[str, Any]:
    return {
        "version": __version__,
        "host": versions.version_text(versions.HOST),
        "default": versions.version_text(versions.DEFAULT),
        "releases": [
            {"version": versions.version_text(v), "readable": versions.readable(v)}
            for v in versions.RELEASES
        ],
    }


def list_levels(
    python: tuple[int, int] | None = None,
    animal: str | None = None,
    extra: dict[str, Level] | None = None,
) -> list[dict[str, Any]]:
    """Every level; titles name the items of ``animal`` where it can play the level.

    ``extra`` adds levels that are not files of the package (a class's own levels).
    """
    levels = []
    extra = extra or {}
    for level in [*_all_levels(), *extra.values()]:
        levels.append(
            {
                "id": level.id,
                "title": level.title_for(animal),
                "module": level.module,
                "animal": level.animal,
                "signature": level.signature,
                "cub": level.cub,
                "worlds": len(level.worlds()),
                "minPython": versions.version_text(level.min_python) if level.min_python else None,
                "locked": lock_reason(level, python),
            }
        )
        if level.id in extra:
            levels[-1]["own"] = True  # the class's own level (classroom hub)
    return levels


LEVEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")


def _find_level(level_id: str, extra: dict[str, Level] | None = None) -> Level:
    """A level by id only: an API request never names a file (``find_level`` also would)."""
    if not LEVEL_ID.match(level_id):
        raise LevelError(f"No level called {level_id!r}.")
    return (extra or {}).get(level_id) or find_level(level_id)


def get_level(
    level_id: str,
    animal: str | None = None,
    python: tuple[int, int] | None = None,
    extra: dict[str, Level] | None = None,
) -> dict[str, Any]:
    if animal is not None and animal not in animal_names():
        animal = None
    try:
        level = _find_level(level_id, extra)
        return level_to_json(level, animal, python)
    except LevelError as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None


def api_parse(body: dict[str, Any]) -> dict[str, Any]:
    source = _text(body, "source")
    result = parse(source, _python(body.get("python")))
    return {
        "ok": result.ok,
        "diagnostics": [asdict(d) for d in result.diagnostics],
        "program": ir.to_dict(result.program) if result.program else None,
        "positions": {node_id: asdict(span) for node_id, span in result.positions.items()},
    }


def api_print(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("program")
    if not isinstance(data, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "`program` must be an IR object")
    try:
        program = ir.from_dict(data)
        if not isinstance(program, ir.Program):
            raise TypeError("the top node must be a Program")
        printed = print_program(program)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"not a valid program: {exc}") from None
    return {
        "text": printed.text,
        "sourceMap": {node_id: asdict(span) for node_id, span in printed.source_map.items()},
    }


def _watch_list(value: Any) -> list[str]:
    """The expressions the child watches in the debugger: a few short texts."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and 0 < len(item) <= 60][:5]


def _modules(body: dict[str, Any]) -> dict[str, str]:
    modules = body.get("modules") or {}
    ok = isinstance(modules, dict) and len(modules) <= MAX_MODULES
    ok = ok and all(
        isinstance(k, str) and k.isidentifier() and isinstance(v, str) for k, v in modules.items()
    )
    if not ok:
        raise ApiError(HTTPStatus.BAD_REQUEST, "`modules` must map helper names to Python text")
    return modules


def _inline_level(data: Any) -> Level:
    """A level sent by the editor; checked like a level file before it runs."""
    report = validate_level_data(data, has_solution=True)
    if not report.ok:
        raise ApiError(HTTPStatus.BAD_REQUEST, "; ".join(report.errors))
    return Level.from_dict(data)


def api_run(
    body: dict[str, Any], store: ProfileStore, extra: dict[str, Level] | None = None
) -> dict[str, Any]:
    source = _text(body, "source")
    animal = body.get("animal")
    player = body.get("profile")
    variant = body.get("variant", 0)
    if isinstance(variant, bool) or not isinstance(variant, int):
        raise ApiError(HTTPStatus.BAD_REQUEST, "`variant` must be a whole number")
    if animal is not None and not isinstance(animal, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, "`animal` must be text")
    try:
        if "levelData" in body:
            level = _inline_level(body["levelData"])
        else:
            level_id = _text(body, "level")
            level = _find_level(level_id, extra)
        run = run_level(
            level,
            source,
            animal=animal,
            variant=variant,
            modules=_modules(body),
            python=_python(body.get("python")),
            watch=True,
            watch_expressions=_watch_list(body.get("watch")),
        )
    except LevelError as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None
    data = run_to_json(run)
    if body.get("save") and run.result is not None:
        data["savedRun"] = make_run(run, source)
    if isinstance(player, str) and player and "levelData" not in body:
        data["progress"] = store.record(player, attempt_from_run(run, source))
        levels = _all_levels()
        # stickers come with a solved run, never right after a failed one (a player who
        # earned one earlier gets it with their next success)
        solved = run.check is not None and run.check.solved
        data["newStickers"] = store.award(player, levels) if solved else []
        data["suggestion"] = store.suggest(player, level, levels)
        # pilot (phase 6): the first star's time and hints used; an "after" check when due
        check = pilot.record_run(store, player, level, solved, body.get("hints"), levels)
        if check:
            data["pilotCheck"] = check  # "check" is the goal check of the run
    return data


def api_story(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"html": storybook_html(body.get("run"))}
    except RunFileError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from None


def api_animals() -> list[dict[str, Any]]:
    return [load_pack(name).public() for name in animal_names()]


def api_unlock(profile_id: str, body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    levels = _all_levels()
    card = card_for_code(_text(body, "code"), levels)
    if card is None:
        raise ProfileError(t("That code doesn't match any card. Check the spelling."))
    return {"card": card_public(card, levels), **store.unlock_card(profile_id, card)}


def api_set_habitat(profile_id: str, body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    outfit = body.get("outfit")
    if outfit is not None and not isinstance(outfit, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, "`outfit` must be text")
    return store.set_habitat(profile_id, body.get("placed"), outfit)


def api_check_level(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("level")
    solution = _text(body, "solution")
    report = validate_level_data(data, has_solution=True)
    if not report.ok:
        return {"ok": False, "errors": report.errors}
    errors = solution_errors(Level.from_dict(data), solution)
    return {"ok": not errors, "errors": errors}


# --- players and grown-ups --------------------------------------------------------------


def _all_levels() -> list[Level]:
    levels = []
    for path in level_files():
        try:
            levels.append(load_level(path))
        except LevelError:
            continue
    return levels


def api_profiles(store: ProfileStore) -> dict[str, Any]:
    players = []
    for profile in store.profiles():
        levels = store.progress(profile.id)["levels"]
        players.append(
            {
                **asdict(profile),
                "stars": sum(entry.get("stars", 0) for entry in levels.values()),
                "solved": sum(1 for entry in levels.values() if entry.get("solved")),
            }
        )
    return {
        "profiles": players,
        "pictures": list(store.pictures),
        "parent": store.parent().public(),
    }


def api_add_profile(body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    cub = body.get("cub") is True  # Cub mode (ages 6-8), ticked when the player is added
    return asdict(store.add(_text(body, "name"), _text(body, "picture"), cub=cub))


def api_progress(profile_id: str, store: ProfileStore) -> dict[str, Any]:
    data = store.progress(profile_id)
    levels = data["levels"]
    return {
        "cub": store.find(profile_id).cub,
        "stickers": len(data.get("stickers", [])),
        "outfit": data.get("outfit", "none"),
        "levels": {
            level_id: {"stars": entry.get("stars", 0), "solved": entry.get("solved", False)}
            for level_id, entry in levels.items()
        },
        "today": store.today_status(profile_id),
        "pilot": pilot.enabled(store),
        "smileyDue": pilot.smiley_due(store, profile_id),
    }


def api_time(profile_id: str, body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    seconds = body.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        raise ApiError(HTTPStatus.BAD_REQUEST, "`seconds` must be a number")
    return store.add_time(profile_id, seconds)


PARENT_ACTIONS = (
    "check", "settings", "report", "export", "remove", "import", "pilot-export", "age", "cub",
)  # fmt: skip


def api_parent(action: str, body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    if action not in PARENT_ACTIONS:
        raise ApiError(HTTPStatus.NOT_FOUND, "no such API")
    pin = body.get("pin")
    pin = str(pin) if pin not in (None, "") else None
    if action == "check":
        store.check_pin(pin)
        return {"ok": True, "parent": store.parent().public()}
    if action == "settings":
        minutes = body["dailyMinutes"] if "dailyMinutes" in body else "keep"
        settings = store.update_parent(
            pin=pin,
            daily_minutes=minutes,
            private_mode=body.get("privateMode"),
            new_pin=body.get("newPin") or None,
            clear_pin=bool(body.get("clearPin")),
            pilot=body.get("pilot"),
        )
        return settings.public()
    store.check_pin(pin)
    if action == "import":  # a player brought home from a class, or from another computer
        data = body.get("data")
        if not isinstance(data, dict):
            raise ProfileError(t("This is not a CodeZoo profile file."))
        return asdict(store.import_(data))
    if action == "pilot-export":  # anonymised, for the pilot (phase 6)
        data = pilot.export(store, _all_levels())
        return {"file": data, "contents": pilot.describe_export(data)}
    player = _text(body, "profile")
    if action == "age":
        return pilot.set_age_band(store, player, body.get("ageBand"))
    if action == "cub":  # Cub mode on or off for one player (phase 7)
        return asdict(store.set_cub(player, body.get("on") is True))
    if action == "report":
        report = store.report(player, _all_levels())
        report["pilot"] = pilot_summary(store, player)
        return report
    if action == "export":
        return store.export(player)
    if action == "remove":
        return {"removed": asdict(store.remove(player))}
    raise ApiError(HTTPStatus.NOT_FOUND, "no such API")


def pilot_summary(store: ProfileStore, player: str) -> dict[str, Any] | None:
    """The pilot id, age band and concept checks (right answers before and after)."""
    data = store.progress(player).get("pilot")
    if not data:
        return None
    checks = {
        module: {phase: (r["right"], r["of"]) for phase, r in done.items() if not r["skipped"]}
        for module, done in data.get("checks", {}).items()
    }
    return {"id": data["id"], "ageBand": data.get("ageBand"), "checks": checks}


def api_pilot_event(
    profile_id: str, body: dict[str, Any], store: ProfileStore, extra: dict[str, Level] | None
) -> dict[str, Any]:
    event = body.get("event")
    if event == "open":
        level_id = _text(body, "level")
        try:
            level = _find_level(level_id, extra)
        except LevelError as exc:
            raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None
        return pilot.record_open(store, profile_id, level, _all_levels())
    return pilot.record_event(store, profile_id, event, body.get("value"))


def api_games() -> list[dict[str, Any]]:
    return [
        {
            "id": spec.id,
            "title": spec.title_text(),
            "template": spec.template,
            "animal": spec.animal,
        }
        for spec in gamemode.all_games()
    ]


def api_game(game_id: str, animal: str | None) -> dict[str, Any]:
    if not GAME_ID.match(game_id):
        raise ApiError(HTTPStatus.NOT_FOUND, f"no game called {game_id!r}")
    try:
        return gamemode.game_to_json(gamemode.find_game(game_id), animal)
    except gamemode.GameError as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None


def _game_spec(body: dict[str, Any]) -> gamemode.GameSpec:
    """The game a request names: a bundled game's id, or a whole game (``gameData``) from
    the world editor, a share link or a class share."""
    try:
        if "gameData" in body:
            return gamemode.GameSpec.from_dict(body["gameData"])
        game_id = body.get("game")
        if not isinstance(game_id, str) or not GAME_ID.match(game_id):
            raise ApiError(HTTPStatus.BAD_REQUEST, "game must be a game id")
        return gamemode.find_game(game_id)
    except (gamemode.GameError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from None


def _source(body: dict[str, Any]) -> str:
    source = body.get("source", "")
    if not isinstance(source, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, "source must be text")
    return source


def _animal(body: dict[str, Any]) -> str | None:
    animal = body.get("animal")
    return animal if isinstance(animal, str) and animal in animal_names() else None


def api_game_test(body: dict[str, Any], seconds: float = 20.0) -> dict[str, Any]:
    """ "Test my game": the playtest bot plays it ``games`` times (30 unless asked)."""
    spec = _game_spec(body)
    games = body.get("games", gamemode.BOT_GAMES)
    if isinstance(games, bool) or not isinstance(games, int):
        games = gamemode.BOT_GAMES
    return gamemode.playtest(
        spec, _source(body), games=games, animal=_animal(body), seconds=seconds
    )


def api_game_start(body: dict[str, Any]) -> dict[str, Any]:
    spec = _game_spec(body)
    source = _source(body)
    seed = body.get("seed", 0)
    game = gamemode.Game(
        spec,
        source,
        animal=_animal(body),
        seed=seed if isinstance(seed, int) and not isinstance(seed, bool) else 0,
        version=_python(body.get("python")),
    )
    result = game.start()
    return {"session": gamemode.SESSIONS.add(game), **game.to_json(result)}


def api_game_tick(body: dict[str, Any]) -> dict[str, Any]:
    game = gamemode.SESSIONS.get(body.get("session"))
    if game is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "that game has ended; start it again")
    keys = body.get("keys", [])
    if not isinstance(keys, list):
        raise ApiError(HTTPStatus.BAD_REQUEST, "keys must be a list")
    return game.to_json(game.tick([key for key in keys if isinstance(key, str)]))


# --- playing together (G3) ------------------------------------------------------------


def _room_player(body: dict[str, Any], store: ProfileStore) -> tuple[str, str, str]:
    """Who is joining: a player of this family or class, or else a numbered guest."""
    profile = body.get("profile")
    if isinstance(profile, str):
        for found in store.profiles():
            if found.id == profile:
                return found.id, found.name, found.picture
    return f"guest-{secrets.token_hex(3)}", t("Guest"), ""


def _look(body: dict[str, Any]) -> str:
    look = body.get("look")
    return look if isinstance(look, str) and look in animal_names() else ""


def _seat_answer(room: gamerooms.Room, seat: gamerooms.Seat) -> dict[str, Any]:
    """A seat in a room, and the room's game to draw (it may not be the one on screen)."""
    return {
        "room": room.public(),
        "seat": seat.token,
        "number": room.number(seat),
        "game": gamemode.game_to_json(room.spec),
    }


def api_room(action: str, body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    rooms = gamerooms.ROOMS
    try:
        if action == "open":
            spec = _game_spec(body)
            source = _source(body)
            profile, name, picture = _room_player(body, store)
            title = " ".join(str(body.get("title") or "").split())[:60] or spec.title_text()
            room = rooms.open(spec, source, title)
            return _seat_answer(room, room.join(profile, name, picture, _look(body)))
        room = rooms.get(body.get("room"))
        if action == "join":
            profile, name, picture = _room_player(body, store)
            return _seat_answer(room, room.join(profile, name, picture, _look(body)))
        if action == "start":
            return room.start(body.get("seat"), version=_python(body.get("python")))
        if action == "keys":
            room.keys(body.get("seat"), body.get("keys"))
            return {"ok": True}
        if action == "react":
            room.react(body.get("seat"), body.get("emoji"))
            return {"ok": True}
        if action == "leave":
            room.leave(body.get("seat"))
            return {"ok": True}
    except gamerooms.RoomError as exc:
        raise ApiError(HTTPStatus.CONFLICT, str(exc)) from None
    raise ApiError(HTTPStatus.NOT_FOUND, "no such API")


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"`{key}` must be text")
    return value


def dispatch(
    method: str,
    path: str,
    query: dict[str, str],
    body: dict[str, Any],
    store: ProfileStore,
    extra_levels: dict[str, Level] | None = None,
) -> Any:
    """Answer one API request; raises ``ApiError``, ``PinError`` or ``ProfileError``.

    ``extra_levels`` are levels that aren't package files (the classroom hub's own).
    """
    if method == "GET":
        python = _python(query.get("python"))
        if path == "/api/levels":
            animal = query.get("animal")
            return list_levels(python, animal if animal in animal_names() else None, extra_levels)
        if path == "/api/info":
            return api_info()
        if path == "/api/profiles":
            return api_profiles(store)
        if match := PROGRESS_PATH.match(path):
            return api_progress(match["id"], store)
        if match := HABITAT_PATH.match(path):
            return store.habitat(match["id"])
        if path == "/api/animals":
            return api_animals()
        if path == "/api/games":
            return api_games()
        if path.startswith("/api/games/"):
            return api_game(unquote(path.removeprefix("/api/games/")), query.get("animal"))
        if path == "/api/rooms":
            return {"rooms": gamerooms.ROOMS.list(), "reactions": list(gamerooms.REACTIONS)}
        if path == "/api/room/events":
            try:
                return gamerooms.EventStream(gamerooms.ROOMS.get(query.get("room")))
            except gamerooms.RoomError as exc:
                raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None
        if match := QUESTIONS_PATH.match(path):
            return {"module": match["module"], "questions": pilot.questions(match["module"])}
        if path.startswith("/api/levels/"):
            return get_level(
                unquote(path.removeprefix("/api/levels/")),
                query.get("animal"),
                python,
                extra_levels,
            )
        raise ApiError(HTTPStatus.NOT_FOUND, "no such API")
    if path == "/api/parse":
        return api_parse(body)
    if path == "/api/print":
        return api_print(body)
    if path == "/api/run":
        return api_run(body, store, extra_levels)
    if path == "/api/pond":  # the console's >>> prompt (repl.py)
        from mse_codezoo.repl import PONDS

        return PONDS.feed(body.get("session"), body.get("line"), _python(body.get("python")))
    if path == "/api/profiles":
        return api_add_profile(body, store)
    if match := TIME_PATH.match(path):
        return api_time(match["id"], body, store)
    if match := PARENT_PATH.match(path):
        return api_parent(match["action"], body, store)
    if match := UNLOCK_PATH.match(path):
        return api_unlock(match["id"], body, store)
    if match := HABITAT_PATH.match(path):
        return api_set_habitat(match["id"], body, store)
    if match := PICTURE_PATH.match(path):
        return asdict(store.set_picture(match["id"], _text(body, "picture")))
    if match := PILOT_PATH.match(path):
        return api_pilot_event(match["id"], body, store, extra_levels)
    if match := CHECK_PATH.match(path):
        return pilot.answer_check(
            store, match["id"], _text(body, "module"), _text(body, "phase"), body.get("answers")
        )
    if path == "/api/story":
        return api_story(body)
    if path == "/api/game/start":
        return api_game_start(body)
    if path == "/api/game/tick":
        return api_game_tick(body)
    if path == "/api/game/stop":
        gamemode.SESSIONS.stop(body.get("session"))
        return {"ok": True}
    if path == "/api/game/test":
        return api_game_test(body)
    if path == "/api/game/preview":
        return gamemode.game_to_json(_game_spec(body), _animal(body))
    if path.startswith("/api/room/") and ROOM_ACTION.match(path.removeprefix("/api/room/")):
        return api_room(path.removeprefix("/api/room/"), body, store)
    if path == "/api/levels/check":
        return api_check_level(body)
    if path == "/api/levels/preview":
        animal = body.get("animal")
        if animal is not None and animal not in animal_names():
            animal = None
        level = _inline_level(body.get("level"))
        return level_to_json(level, animal, _python(body.get("python")))
    raise ApiError(HTTPStatus.NOT_FOUND, "no such API")


def dispatch_json(
    method: str, path: str, query_json: str, body_json: str, store: ProfileStore, lang: str
) -> str:
    """``dispatch`` with JSON in and out, for the offline build's web worker."""
    query = json.loads(query_json or "{}")
    body = json.loads(body_json or "{}")
    if path.startswith(("/api/room/", "/api/rooms")):
        message = "Playing together needs a classroom hub on the local network."
        return json.dumps({"status": 404, "data": {"error": message}})
    with use_lang(lang):
        try:
            return json.dumps({"status": 200, "data": dispatch(method, path, query, body, store)})
        except ApiError as exc:
            return json.dumps({"status": int(exc.status), "data": {"error": exc.message}})
        except PinError as exc:
            return json.dumps({"status": 403, "data": {"error": str(exc)}})
        except ProfileError as exc:
            return json.dumps({"status": 400, "data": {"error": str(exc)}})


class Handler(BaseHTTPRequestHandler):
    server_version = f"codezoo/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    # --- routing ---------------------------------------------------------------

    def _lang(self, body: dict[str, Any] | None = None) -> str:
        query = parse_qs(urlsplit(self.path).query).get("lang")
        if query:
            return normalize(query[0])
        if body and isinstance(body.get("lang"), str):
            return normalize(body["lang"])
        return from_accept_language(self.headers.get("Accept-Language"))

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        with use_lang(self._lang()):
            self._get()

    def _get(self) -> None:
        path = urlsplit(self.path).path
        try:
            store = self.server.store  # type: ignore[attr-defined]
            if path == "/cards.html":
                self._cards()
            elif path.startswith("/api/"):
                query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
                answer = self._dispatch("GET", path, query, {}, store)
                if isinstance(answer, gamerooms.EventStream):
                    self._stream(answer)
                else:
                    self._json(answer)
            else:
                self._static(path)
        except ApiError as exc:
            self._json({"error": exc.message}, exc.status)
        except PinError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except ProfileError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        path = urlsplit(self.path).path
        store = self.server.store  # type: ignore[attr-defined]
        try:
            raw = self._read_body()  # always read first: replying early resets the connection
            body = self._parse_body(raw)
            with use_lang(self._lang(body)):
                self._json(self._dispatch("POST", path, {}, body, store))
        except ApiError as exc:
            self._json({"error": exc.message}, exc.status)
        except PinError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except ProfileError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _dispatch(
        self, method: str, path: str, query: dict[str, str], body: dict[str, Any], store: Any
    ) -> Any:
        hub = getattr(self.server, "hub", None)
        if hub is None:
            return dispatch(method, path, query, body, store)
        # the classroom hub checks the class code or the teacher's key first (see hub.py)
        return hub.handle(method, path, query, body, self.headers, self.client_address[0])

    def _cards(self) -> None:
        animal = parse_qs(urlsplit(self.path).query).get("animal", ["monkey"])[0]
        if animal not in animal_names():
            raise ApiError(HTTPStatus.NOT_FOUND, "no such animal")
        self._html(cards_html(animal, _all_levels()))

    def _html(self, text: str) -> None:
        payload = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    # --- helpers ---------------------------------------------------------------

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if 0 <= length <= MAX_BODY:
            return self.rfile.read(length)
        if 0 < length <= DRAIN_LIMIT:
            remaining = length
            while remaining > 0:  # discard it so the client can read our answer
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
        else:
            self.close_connection = True
        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")

    def _parse_body(self, raw: bytes) -> dict[str, Any]:
        try:
            data = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "request body must be JSON") from None
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
        return data

    def _json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _stream(self, stream: gamerooms.EventStream) -> None:
        """Server-sent events: one ``data:`` line per message, a comment to keep alive."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        messages = stream.messages()
        try:
            for message in messages:
                text = ": still here\n\n" if message is None else f"data: {json.dumps(message)}\n\n"
                self.wfile.write(text.encode("utf-8"))
                self.wfile.flush()
        except OSError:
            pass  # the device went away
        finally:
            messages.close()

    def _static(self, path: str) -> None:
        relative = unquote(path).lstrip("/") or "index.html"
        root = WEB_DIR.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".js":
            content_type = "text/javascript"
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)


class CodeZooServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        verbose: bool = False,
        store: ProfileStore | None = None,
        hub: Any = None,
    ):
        super().__init__((host, port), Handler)
        self.verbose = verbose
        self.store = store if store is not None else ProfileStore()
        self.hub = hub  # a classroom hub (hub.Hub) answers the API instead, on the network

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{'localhost' if host in ('127.0.0.1', '::1') else host}:{port}/"
