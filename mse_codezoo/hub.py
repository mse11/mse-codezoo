"""The classroom hub behind ``codezoo class serve`` (phase 5): one class on the local network.

The teacher's computer runs the usual web server, listening on the local network instead
of only on this computer. Children open the hub's address (or scan the QR code on the
teacher's screen with their device's own camera app) and join with the class code; the
engine, the levels and the class's players all live on the teacher's computer. Nothing
goes to the internet.

Two keys guard the API:

* the **class code** (``X-Class-Code`` header), shown on the teacher's screen; a new one
  is made every time the hub starts and when the teacher ends the class. Wrong codes are
  counted per device, and too many in a row wait a few minutes.
* the **teacher's key** (``X-Teacher-Token``), printed in the terminal as part of the
  teacher page's address; only the teacher screen has it.

Routes on top of ``server.dispatch``:

    POST /api/class/join {code}             -> the class, its players, free pictures
    GET  /api/class/state                   -> paused, locked, assigned levels, shares count
    POST /api/class/me {picture, name?}     -> a new player (when children may add themselves)
    POST /api/class/import {data}           -> a player from a home export file
    POST /api/class/export {profile}        -> that player's progress, to take home
    GET  /api/class/shares                  -> programs and levels the teacher approved
    POST /api/class/share {profile, kind, title, payload}
    POST /api/class/report {share}          -> hides a share until the teacher looks at it

    GET  /api/teacher/overview              -> everything the teacher's screen shows
    POST /api/teacher/settings {roster?, names?, deleteAtEnd?, locked?, assigned?}
    POST /api/teacher/pause {paused}
    POST /api/teacher/player {name, picture}          (also /rename, /remove, /report, /export)
    POST /api/teacher/level {level, solution}         (also /remove {id})
    POST /api/teacher/share {share, status}           approved | rejected | deleted
    POST /api/teacher/export                -> the whole class as one file
    POST /api/teacher/code                  -> a new class code
    POST /api/teacher/end                   -> ends the class (a workshop deletes its data)

Grown-up routes (``/api/parent/*``) and adding players through ``/api/profiles`` are closed
in a class: the teacher's screen does that. Standard library only.
"""

from __future__ import annotations

import hmac
import secrets
import socket
import threading
import time
from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from mse_codezoo import qr
from mse_codezoo.classes import (
    CLASS_PICTURES,
    LEVEL_ID,
    ClassError,
    ClassInfo,
    ClassStore,
    new_code,
    normalize_code,
)
from mse_codezoo.i18n import t
from mse_codezoo.profiles import MISTAKE_KINDS, PRACTICE_AFTER, ProfileStore, module_name
from mse_codezoo.server import ApiError, _all_levels, dispatch, list_levels

MAX_FAILURES = 10  # wrong class codes from one device ...
FAILURE_WINDOW = 300  # ... within this many seconds, then it waits
LOCKED = HTTPStatus.LOCKED  # 423: the class is paused


def local_address() -> str:
    """This computer's address on the local network (no packet is sent)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


class Hub:
    def __init__(
        self,
        classes: ClassStore,
        class_ref: str,
        *,
        base_url: str = "/",
        on_end: Callable[[], None] | None = None,
    ) -> None:
        self.classes = classes
        self.class_id = classes.find(class_ref).id
        self.base_url = base_url  # "http://192.168.1.20:8765/": what the QR code points to
        self.on_end = on_end
        self.code = new_code()
        self.teacher_token = secrets.token_urlsafe(18)
        self.paused = False
        self.ended = False
        self.lock = threading.RLock()  # one request at a time: files stay consistent
        self.failures: dict[str, list[float]] = {}

    # --- addresses -------------------------------------------------------------------

    @property
    def join_url(self) -> str:
        return f"{self.base_url}?class={self.code}"

    @property
    def teacher_url(self) -> str:
        return f"{self.base_url}teacher.html#key={self.teacher_token}"

    # --- the class ---------------------------------------------------------------------

    def info(self) -> ClassInfo:
        return self.classes.find(self.class_id)

    def players(self) -> ProfileStore:
        return self.classes.players(self.class_id)

    def _public(self) -> dict[str, Any]:
        info = self.info()
        store = self.players()
        profiles = store.profiles()
        used = {p.picture for p in profiles}
        return {
            "class": info.public(),
            "players": [{"id": p.id, "name": p.name, "picture": p.picture} for p in profiles],
            "pictures": list(CLASS_PICTURES),
            "free": [p for p in CLASS_PICTURES if p not in used],
            "paused": self.paused,
        }

    def _state(self) -> dict[str, Any]:
        info = self.info()
        return {
            "name": info.name,
            "type": info.type,
            "paused": self.paused,
            "locked": bool(info.settings["locked"]),
            "assigned": list(info.settings["assigned"]),
            "shares": len(self.classes.shares(self.class_id, "approved")),
        }

    # --- requests ----------------------------------------------------------------------

    def handle(
        self,
        method: str,
        path: str,
        query: dict[str, str],
        body: dict[str, Any],
        headers: Mapping[str, str],
        client: str,
    ) -> Any:
        with self.lock:
            if path == "/api/info" and method == "GET":
                data = dispatch(method, path, query, body, self.players())
                if not self.ended:
                    info = self.info()
                    data["hub"] = {"name": info.name, "type": info.type}
                return data
            if path.startswith("/api/teacher/"):
                self._check_teacher(headers)
                if self.ended:
                    raise ApiError(HTTPStatus.GONE, t("This class has ended."))
                return self._teacher(method, path.removeprefix("/api/teacher/"), body)
            if self.ended:
                raise ApiError(HTTPStatus.GONE, t("This class has ended. Thank you for playing!"))
            if path == "/api/class/join" and method == "POST":
                return self._join(body, client)
            if not self._is_teacher(headers):  # the teacher may open levels and the editor
                self._check_code(headers)
            if path.startswith("/api/class/"):
                return self._class(method, path.removeprefix("/api/class/"), body)
            return self._game(method, path, query, body)

    def _is_teacher(self, headers: Mapping[str, str]) -> bool:
        key = headers.get("X-Teacher-Token") or ""
        return hmac.compare_digest(key.encode(), self.teacher_token.encode())

    def _check_teacher(self, headers: Mapping[str, str]) -> None:
        if not self._is_teacher(headers):
            raise ApiError(HTTPStatus.FORBIDDEN, t("This is the teacher's screen."))

    def _check_code(self, headers: Mapping[str, str]) -> None:
        code = normalize_code(headers.get("X-Class-Code") or "")
        if not hmac.compare_digest(code.encode(), self.code.encode()):
            raise ApiError(
                HTTPStatus.FORBIDDEN,
                t("Join the class first: type the class code from the teacher's screen."),
            )

    def _join(self, body: dict[str, Any], client: str) -> dict[str, Any]:
        now = time.monotonic()
        recent = [s for s in self.failures.get(client, []) if now - s < FAILURE_WINDOW]
        self.failures[client] = recent
        if len(recent) >= MAX_FAILURES:
            raise ApiError(
                HTTPStatus.TOO_MANY_REQUESTS,
                t("Too many wrong codes. Wait a few minutes, then try again."),
            )
        code = normalize_code(body.get("code") or "")
        if not hmac.compare_digest(code.encode(), self.code.encode()):
            recent.append(now)
            raise ApiError(
                HTTPStatus.FORBIDDEN, t("That class code isn't right. Check the teacher's screen.")
            )
        self.failures.pop(client, None)
        return {**self._public(), "code": self.code}

    def _game(self, method: str, path: str, query: dict[str, str], body: dict[str, Any]) -> Any:
        """The usual routes, with the class's players and levels and the teacher's rules."""
        # the grown-up area and the family player list (with everyone's stars) are closed
        if path.startswith("/api/parent/") or path == "/api/profiles":
            raise ApiError(
                HTTPStatus.FORBIDDEN, t("In a class, the teacher's screen has these settings.")
            )
        if method == "GET" and path.startswith("/api/levels/"):
            if not LEVEL_ID.match(unquote(path.removeprefix("/api/levels/"))):
                raise ApiError(HTTPStatus.NOT_FOUND, "no such level")
        info = self.info()
        assigned = list(info.settings["assigned"])
        locked = bool(info.settings["locked"]) and bool(assigned)
        if method == "POST" and path == "/api/run":
            if self.paused:
                raise ApiError(LOCKED, t("The teacher paused the class. Eyes on the teacher!"))
            if locked and ("levelData" in body or body.get("level") not in assigned):
                raise ApiError(
                    HTTPStatus.FORBIDDEN,
                    t("Today the class plays the levels the teacher picked."),
                )
        extra = self.classes.levels(self.class_id)
        data = dispatch(method, path, query, body, self.players(), extra)
        if method == "GET" and path == "/api/levels":
            for level in data:
                level["assigned"] = level["id"] in assigned
            if locked:
                order = {level_id: i for i, level_id in enumerate(assigned)}
                data = sorted((lv for lv in data if lv["assigned"]), key=lambda lv: order[lv["id"]])
        return data

    # --- children ----------------------------------------------------------------------

    def _class(self, method: str, route: str, body: dict[str, Any]) -> Any:
        info = self.info()
        store = self.players()
        if method == "GET" and route == "state":
            return self._state()
        if method == "GET" and route == "shares":
            return {"shares": self.classes.shares(self.class_id, "approved")}
        if method != "POST":
            raise ApiError(HTTPStatus.NOT_FOUND, "no such API")
        if route == "me":
            if info.settings["roster"]:
                raise ApiError(
                    HTTPStatus.FORBIDDEN,
                    t("Pick your picture from the list. Ask the teacher if it is missing."),
                )
            picture = body.get("picture")
            if picture not in CLASS_PICTURES:
                raise ClassError(t("Pick a picture first."))
            if any(p.picture == picture for p in store.profiles()):
                raise ClassError(t("Someone already has that picture. Pick another one."))
            name = body.get("name") if info.settings["names"] else None
            name = " ".join(str(name or "").split()) or picture
            profile = store.add(name, picture)
            return {"id": profile.id, "name": profile.name, "picture": profile.picture}
        if route == "import":
            if info.settings["roster"]:
                raise ApiError(
                    HTTPStatus.FORBIDDEN,
                    t("Pick your picture from the list. Ask the teacher if it is missing."),
                )
            data = body.get("data")
            if not isinstance(data, dict):
                raise ClassError(t("This is not a CodeZoo profile file."))
            used = {p.picture for p in store.profiles()}
            free = [p for p in CLASS_PICTURES if p not in used]
            info_part = dict(data.get("profile") or {})
            if info_part.get("picture") in used or info_part.get("picture") not in CLASS_PICTURES:
                if not free:
                    raise ClassError(t("Every picture is taken. Ask the teacher for help."))
                info_part["picture"] = free[0]
            profile = store.import_({**data, "profile": info_part})
            return {"id": profile.id, "name": profile.name, "picture": profile.picture}
        if route == "export":
            return store.export(_text(body, "profile"))
        if route == "share":
            return self.classes.share(
                self.class_id,
                _text(body, "profile"),
                _text(body, "kind"),
                body.get("title"),
                body.get("payload"),
            )
        if route == "report":
            share_id = _text(body, "share")
            approved = {s["id"] for s in self.classes.shares(self.class_id, "approved")}
            if share_id not in approved:
                raise ClassError(t("That share doesn't exist any more."))
            self.classes.set_share(self.class_id, share_id, "reported")
            return {"ok": True}
        raise ApiError(HTTPStatus.NOT_FOUND, "no such API")

    # --- the teacher -------------------------------------------------------------------

    def _teacher(self, method: str, route: str, body: dict[str, Any]) -> Any:
        if method == "GET" and route == "overview":
            return self.overview()
        if method != "POST":
            raise ApiError(HTTPStatus.NOT_FOUND, "no such API")
        store = self.players()
        if route == "settings":
            changes = {
                key: body.get(key)
                for key in ("roster", "names", "deleteAtEnd", "locked", "assigned")
            }
            self.classes.update(self.class_id, **changes)
            return self.overview()
        if route == "pause":
            self.paused = bool(body.get("paused"))
            return self._state()
        if route == "player":
            profile = store.add(_text(body, "name"), _text(body, "picture"))
            return {"id": profile.id, "name": profile.name, "picture": profile.picture}
        if route == "player/rename":
            profile = store.rename(_text(body, "profile"), _text(body, "name"))
            return {"id": profile.id, "name": profile.name, "picture": profile.picture}
        if route == "player/remove":
            removed = store.remove(_text(body, "profile"))
            return {"removed": removed.id}
        if route == "player/report":
            return store.report(_text(body, "profile"), self._levels())
        if route == "player/export":
            return store.export(_text(body, "profile"))
        if route == "export":
            return self.classes.export(self.class_id)
        if route == "level":
            errors = self.classes.add_level(self.class_id, body.get("level"), body.get("solution"))
            return {"ok": not errors, "errors": errors}
        if route == "level/remove":
            self.classes.remove_level(self.class_id, _text(body, "id"))
            return {"ok": True}
        if route == "share":
            status = _text(body, "status")
            if status not in ("approved", "rejected", "deleted"):
                raise ApiError(
                    HTTPStatus.BAD_REQUEST, "`status` must be approved, rejected or deleted"
                )
            return self.classes.set_share(self.class_id, _text(body, "share"), status)
        if route == "code":
            self.code = new_code()
            self.failures.clear()
            return {"code": self.code, "joinUrl": self.join_url}
        if route == "end":
            return self.end()
        raise ApiError(HTTPStatus.NOT_FOUND, "no such API")

    def end(self) -> dict[str, Any]:
        """End the class: the code stops working; a workshop also deletes its data."""
        info = self.info()
        deleted = bool(info.settings["deleteAtEnd"])
        self.paused = False
        if deleted:
            self.classes.delete(self.class_id)
            self.ended = True
            if self.on_end is not None:
                self.on_end()
            return {"deleted": True, "ended": True}
        self.code = new_code()  # the old code stops working; next session gets a new one
        self.failures.clear()
        return {"deleted": False, "ended": False, "code": self.code, "joinUrl": self.join_url}

    def _levels(self) -> list[Any]:
        return [*_all_levels(), *self.classes.levels(self.class_id).values()]

    def overview(self) -> dict[str, Any]:
        """Everything on the teacher's screen: who is here, how far, who is stuck."""
        info = self.info()
        store = self.players()
        extra = self.classes.levels(self.class_id)
        levels = self._levels()
        titles = {lv["id"]: lv for lv in list_levels(None, None, extra)}
        modules: dict[str, list[str]] = {}
        for level in levels:
            modules.setdefault("mine" if level.id in extra else level.module, []).append(level.id)
        players = []
        concepts: dict[str, dict[str, int]] = {}
        mistakes: dict[str, int] = {}
        reached: dict[str, list[int]] = {}  # level id -> [players who tried, who solved]
        for profile in store.profiles():
            data = store.progress(profile.id)
            entries = data["levels"]
            per_module = {}
            for module, ids in modules.items():
                stars = sum(entries.get(i, {}).get("stars", 0) for i in ids)
                solved = sum(1 for i in ids if entries.get(i, {}).get("solved"))
                if stars or solved or any(i in entries for i in ids):
                    per_module[module] = {"stars": stars, "solved": solved, "levels": len(ids)}
            stuck = [
                {"level": level_id, "title": titles.get(level_id, {}).get("title", level_id),
                 "fails": entry.get("fails", 0)}
                for level_id, entry in entries.items()
                if not entry.get("solved") and entry.get("fails", 0) >= PRACTICE_AFTER
            ]  # fmt: skip
            for level_id, entry in entries.items():
                row = reached.setdefault(level_id, [0, 0])
                row[0] += 1
                row[1] += int(bool(entry.get("solved")))
            for kind, count in data["mistakes"].items():
                mistakes[kind] = mistakes.get(kind, 0) + count
            report = store.report(profile.id, levels)
            for row in report["concepts"]:
                if row["status"] == "not yet":
                    continue
                counts = concepts.setdefault(
                    row["concept"], {"met": 0, "practised": 0, "mastered": 0}
                )
                counts[row["status"]] += 1
            players.append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "picture": profile.picture,
                    "stars": sum(e.get("stars", 0) for e in entries.values()),
                    "solved": sum(1 for e in entries.values() if e.get("solved")),
                    "modules": per_module,
                    "stuck": stuck,
                    "minutesToday": store.today_status(profile.id)["minutesToday"],
                }
            )
        return {
            "class": {**info.public(), "created": info.created, "settings": info.settings},
            "code": self.code,
            "joinUrl": self.join_url,
            "qr": qr.svg(self.join_url, module=6, label=t("Class code")),
            "paused": self.paused,
            "players": players,
            "pictures": list(CLASS_PICTURES),
            "modules": [
                {
                    "id": module,
                    "name": t("Our own levels") if module == "mine" else module_name(module),
                    "levels": [{"id": i, "title": titles.get(i, {}).get("title", i)} for i in ids],
                }
                for module, ids in modules.items()
            ],  # fmt: skip
            "concepts": [{"concept": c, **counts} for c, counts in sorted(concepts.items())],
            "mistakes": [
                {"kind": k, "text": t(MISTAKE_KINDS.get(k, k)), "count": n}
                for k, n in sorted(mistakes.items(), key=lambda kv: -kv[1])[:5]
            ],
            "levelStats": [
                {
                    "level": level_id,
                    "title": titles.get(level_id, {}).get("title", level_id),
                    "tried": tried,
                    "solved": solved,
                }
                for level_id, (tried, solved) in reached.items()
            ],  # fmt: skip
            "levels": [
                {"id": level_id, "title": entry["level"].get("title", level_id)}
                for level_id, entry in self.classes.level_entries(self.class_id).items()
            ],
            "shares": self.classes.shares(self.class_id),
        }


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"`{key}` must be text")
    return value
