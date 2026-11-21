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
    GET  /api/profiles/<id>/progress   stars per level, today's minutes and limit
    POST /api/profiles/<id>/time {seconds} -> today's minutes and limit
    POST /api/parent/<action> {pin?, ...}  check | settings | report | export | remove |
                                       import {data} (a file from `profile export`)

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
"""

from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from mse_codezoo import __version__, ir, versions
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
PARENT_PATH = re.compile(r"^/api/parent/(?P<action>[a-z]+)$")
UNLOCK_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/unlock$")
HABITAT_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/habitat$")
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
                "worlds": len(level.worlds()),
                "minPython": versions.version_text(level.min_python) if level.min_python else None,
                "locked": lock_reason(level, python),
            }
        )
        if level.id in extra:
            levels[-1]["own"] = True  # the class's own level (classroom hub)
    return levels


def get_level(
    level_id: str,
    animal: str | None = None,
    python: tuple[int, int] | None = None,
    extra: dict[str, Level] | None = None,
) -> dict[str, Any]:
    if animal is not None and animal not in animal_names():
        animal = None
    try:
        level = (extra or {}).get(level_id) or find_level(level_id)
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
            level = (extra or {}).get(level_id) or find_level(level_id)
        run = run_level(
            level,
            source,
            animal=animal,
            variant=variant,
            modules=_modules(body),
            python=_python(body.get("python")),
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
    return asdict(store.add(_text(body, "name"), _text(body, "picture")))


def api_progress(profile_id: str, store: ProfileStore) -> dict[str, Any]:
    data = store.progress(profile_id)
    levels = data["levels"]
    return {
        "stickers": len(data.get("stickers", [])),
        "outfit": data.get("outfit", "none"),
        "levels": {
            level_id: {"stars": entry.get("stars", 0), "solved": entry.get("solved", False)}
            for level_id, entry in levels.items()
        },
        "today": store.today_status(profile_id),
    }


def api_time(profile_id: str, body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    seconds = body.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        raise ApiError(HTTPStatus.BAD_REQUEST, "`seconds` must be a number")
    return store.add_time(profile_id, seconds)


PARENT_ACTIONS = ("check", "settings", "report", "export", "remove", "import")


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
        )
        return settings.public()
    store.check_pin(pin)
    if action == "import":  # a player brought home from a class, or from another computer
        data = body.get("data")
        if not isinstance(data, dict):
            raise ProfileError(t("This is not a CodeZoo profile file."))
        return asdict(store.import_(data))
    player = _text(body, "profile")
    if action == "report":
        return store.report(player, _all_levels())
    if action == "export":
        return store.export(player)
    if action == "remove":
        return {"removed": asdict(store.remove(player))}
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
    if path == "/api/story":
        return api_story(body)
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
                self._json(self._dispatch("GET", path, query, {}, store))
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
