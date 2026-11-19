"""Local web server behind ``codezoo serve``: static web client plus a small JSON API.

The browser edits IR JSON and asks the engine to parse, print and run; it never parses
Python itself. Binds to localhost by default. Standard library only.

API (all JSON):
    GET  /api/levels             level list
    GET  /api/levels/<id>        one level, ready to draw
    POST /api/parse   {source}   -> {ok, diagnostics, program, positions}
    POST /api/print   {program}  -> {text, sourceMap}
    POST /api/run     {level, source, animal?, profile?} -> run (as `codezoo run --json`);
                      with a profile, the result is saved to that player's progress
    GET  /api/profiles                 players, pictures, public grown-up settings
    POST /api/profiles {name, picture} -> new player
    GET  /api/profiles/<id>/progress   stars per level, today's minutes and limit
    POST /api/profiles/<id>/time {seconds} -> today's minutes and limit
    POST /api/parent/<action> {pin?, ...}  check | settings | report | export | remove
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
from urllib.parse import unquote, urlsplit

from mse_codezoo import __version__, ir
from mse_codezoo.game import attempt_from_run, level_to_json, run_level, run_to_json
from mse_codezoo.lang_python import parse, print_program
from mse_codezoo.levels import Level, LevelError, find_level, level_files, load_level
from mse_codezoo.profiles import PICTURES, PinError, ProfileError, ProfileStore

WEB_DIR = Path(__file__).parent / "web"
MAX_BODY = 256 * 1024
DRAIN_LIMIT = 8 * 1024 * 1024  # larger bodies are not read; the connection is closed
DEFAULT_PORT = 8765
PROGRESS_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/progress$")
TIME_PATH = re.compile(r"^/api/profiles/(?P<id>p[0-9a-f]{8})/time$")
PARENT_PATH = re.compile(r"^/api/parent/(?P<action>[a-z]+)$")


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def list_levels() -> list[dict[str, Any]]:
    levels = []
    for path in level_files():
        try:
            level = load_level(path)
        except LevelError:
            continue
        levels.append(
            {"id": level.id, "title": level.title, "module": level.module, "animal": level.animal}
        )
    return levels


def get_level(level_id: str) -> dict[str, Any]:
    try:
        return level_to_json(find_level(level_id))
    except LevelError as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None


def api_parse(body: dict[str, Any]) -> dict[str, Any]:
    source = _text(body, "source")
    result = parse(source)
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


def api_run(body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    source = _text(body, "source")
    animal = body.get("animal")
    player = body.get("profile")
    try:
        level = find_level(_text(body, "level"))
        run = run_level(level, source, animal=animal)
    except LevelError as exc:
        raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from None
    data = run_to_json(run)
    if isinstance(player, str) and player:
        data["progress"] = store.record(player, attempt_from_run(run, source))
    return data


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
    return {"profiles": players, "pictures": list(PICTURES), "parent": store.parent().public()}


def api_add_profile(body: dict[str, Any], store: ProfileStore) -> dict[str, Any]:
    return asdict(store.add(_text(body, "name"), _text(body, "picture")))


def api_progress(profile_id: str, store: ProfileStore) -> dict[str, Any]:
    levels = store.progress(profile_id)["levels"]
    return {
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


PARENT_ACTIONS = ("check", "settings", "report", "export", "remove")


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


class Handler(BaseHTTPRequestHandler):
    server_version = f"codezoo/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    # --- routing ---------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = urlsplit(self.path).path
        try:
            store = self.server.store  # type: ignore[attr-defined]
            if path == "/api/levels":
                self._json(list_levels())
            elif path == "/api/profiles":
                self._json(api_profiles(store))
            elif match := PROGRESS_PATH.match(path):
                self._json(api_progress(match["id"], store))
            elif path.startswith("/api/levels/"):
                self._json(get_level(unquote(path.removeprefix("/api/levels/"))))
            elif path.startswith("/api/"):
                raise ApiError(HTTPStatus.NOT_FOUND, "no such API")
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
            self._json(self._post(path, self._parse_body(raw), store))
        except ApiError as exc:
            self._json({"error": exc.message}, exc.status)
        except PinError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except ProfileError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _post(self, path: str, body: dict[str, Any], store: ProfileStore) -> Any:
        if path == "/api/parse":
            return api_parse(body)
        if path == "/api/print":
            return api_print(body)
        if path == "/api/run":
            return api_run(body, store)
        if path == "/api/profiles":
            return api_add_profile(body, store)
        if match := TIME_PATH.match(path):
            return api_time(match["id"], body, store)
        if match := PARENT_PATH.match(path):
            return api_parent(match["action"], body, store)
        raise ApiError(HTTPStatus.NOT_FOUND, "no such API")

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
    ):
        super().__init__((host, port), Handler)
        self.verbose = verbose
        self.store = store if store is not None else ProfileStore()

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{'localhost' if host in ('127.0.0.1', '::1') else host}:{port}/"
