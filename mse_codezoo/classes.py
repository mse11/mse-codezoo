"""Classes and workshops for the classroom hub (phase 5). No cloud, no accounts.

A class lives in its own folder on the teacher's computer: ``<home>/classes/<id>/`` holds
``class.json`` (name, type, settings, the teacher's own levels, shared programs) and the
players, stored exactly like a family's (``profiles.json`` and ``progress/``), so a child's
progress can be exported and imported at home with ``codezoo profile import``.

Two class types set the defaults; the teacher can change every setting:

* **workshop** - a one-off session: children pick any free picture when they join, names
  are optional, and ending the workshop deletes its data.
* **class** - meets regularly: the teacher sets up the list of players, children pick
  themselves from it, and the data is kept between sessions.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mse_codezoo.cards import WORDS
from mse_codezoo.game import solution_errors
from mse_codezoo.i18n import LANGS, t
from mse_codezoo.levels import Level, LevelError, find_level, validate_level_data
from mse_codezoo.profiles import CLASS_PICTURES, ProfileError, ProfileStore, default_home

CLASS_TYPES = ("workshop", "class")
DEFAULTS: dict[str, dict[str, Any]] = {
    # roster: only the teacher adds players; names: children may type a first name
    # cub: new players start in Cub mode (ages 6-8, phase 7)
    "workshop": {"roster": False, "names": True, "deleteAtEnd": True, "cub": False},
    "class": {"roster": True, "names": True, "deleteAtEnd": False, "cub": False},
}
VIEWS = ("2d", "3d")  # the stage: the 2D drawing (any device) and the 3D scene (needs WebGL)
# sounds on the children's devices: both (each child switches), or only "on" or "off"
SOUNDS = ("on", "off")
# colours on the children's devices: both (each child switches), or only "light" or "dark"
THEMES = ("light", "dark")
# the panes under the stage children may use; small children may need only the blocks
PANES = ("blocks", "code", "console")
CLASS_ID = re.compile(r"^c[0-9a-f]{8}$")
LEVEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")
MAX_CLASS_NAME = 40
MAX_LEVELS = 50
MAX_SHARES = 300
MAX_SHARE_BYTES = 200_000
MAX_TITLE = 60
SHARE_KINDS = ("program", "level", "game")
SHARE_STATUSES = ("pending", "approved", "rejected", "reported")


class ClassError(ProfileError):
    """A class request that can't be done, worded for the person using the app."""


def new_code() -> str:
    """A class code that is easy to type on a tablet: ``MANGO-427``."""
    return f"{secrets.choice(WORDS)}-{secrets.randbelow(900) + 100}"


def normalize_code(text: Any) -> str:
    """What a child typed: case, spaces and the dash don't matter."""
    parts = re.findall(r"[A-Za-z]+|\d+", str(text))
    return "-".join(parts).upper()


@dataclass
class ClassInfo:
    id: str
    name: str
    type: str
    created: str
    settings: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "roster": bool(self.settings.get("roster")),
            "names": bool(self.settings.get("names")),
            # the language children's devices open in (None: each device's own); a child
            # can still switch it
            "lang": self.settings.get("lang") if self.settings.get("lang") in LANGS else None,
            # the stage views children may use: both (each child picks), or only "2d" or "3d"
            "views": [v for v in VIEWS if v in self.settings.get("views", VIEWS)] or list(VIEWS),
            # sounds: both (each child switches them), or only "on" or "off"
            "sounds": [v for v in SOUNDS if v in self.settings.get("sounds", SOUNDS)]
            or list(SOUNDS),
            # colours: both (each child switches them), or only "light" or "dark"
            "themes": [v for v in THEMES if v in self.settings.get("themes", THEMES)]
            or list(THEMES),
            # the panes children may use (each child can still hide those); the others are hidden
            "panes": [v for v in PANES if v in self.settings.get("panes", PANES)] or list(PANES),
        }


class ClassStore:
    """Every class on this computer, under ``<home>/classes``."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home is not None else default_home()
        self.root = self.home / "classes"

    # --- files -------------------------------------------------------------------

    def _dir(self, class_id: str) -> Path:
        if not CLASS_ID.match(class_id):
            raise ClassError(t("That class doesn't exist."))
        return self.root / class_id

    def _read(self, class_id: str) -> dict[str, Any]:
        path = self._dir(class_id) / "class.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ClassError(t("That class doesn't exist.")) from None
        except (OSError, json.JSONDecodeError) as exc:
            raise ClassError(t("Can't read {name}: {why}", name=path.name, why=exc)) from None
        data.setdefault("settings", {})
        data.setdefault("levels", {})
        data.setdefault("shares", [])
        return data

    def _write(self, class_id: str, data: dict[str, Any]) -> None:
        folder = self._dir(class_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "class.tmp"
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(folder / "class.json")

    @staticmethod
    def _info(data: dict[str, Any]) -> ClassInfo:
        settings = {**DEFAULTS.get(data["type"], DEFAULTS["class"]), **data["settings"]}
        settings.setdefault("assigned", [])
        settings.setdefault("locked", True)  # saved picks are all children see (Nov 22, 2026)
        return ClassInfo(data["id"], data["name"], data["type"], data["created"], settings)

    # --- classes -----------------------------------------------------------------

    def classes(self) -> list[ClassInfo]:
        if not self.root.is_dir():
            return []
        found = []
        for folder in sorted(self.root.iterdir()):
            if CLASS_ID.match(folder.name) and (folder / "class.json").is_file():
                try:
                    found.append(self._info(self._read(folder.name)))
                except ClassError:
                    continue
        return sorted(found, key=lambda c: (c.created, c.name.casefold()))

    def create(
        self, name: str, class_type: str = "workshop", lang: str | None = None, **settings: Any
    ) -> ClassInfo:
        name = " ".join(str(name).split())
        if not name:
            raise ClassError(t("Please type a name."))
        if len(name) > MAX_CLASS_NAME:
            raise ClassError(t("Names can be at most {count} letters long.", count=MAX_CLASS_NAME))
        if class_type not in CLASS_TYPES:
            raise ClassError(t("A class is a workshop or a class."))
        if any(c.name.casefold() == name.casefold() for c in self.classes()):
            raise ClassError(t("There is already a class called {name}.", name=name))
        class_id = f"c{secrets.token_hex(4)}"
        clean: dict[str, Any] = {
            k: bool(v) for k, v in settings.items() if k in DEFAULTS[class_type]
        }
        if lang is not None:
            if lang not in LANGS:
                raise ClassError(t("Pick one of these languages: {names}.", names=", ".join(LANGS)))
            clean["lang"] = lang
        data = {
            "format": "codezoo-class",
            "version": 1,
            "id": class_id,
            "name": name,
            "type": class_type,
            "created": dt.date.today().isoformat(),
            "settings": clean,
            "levels": {},
            "shares": [],
        }
        self._write(class_id, data)
        return self._info(data)

    def find(self, ref: str) -> ClassInfo:
        """A class by id or by name (any letter case)."""
        for info in self.classes():
            if info.id == ref or info.name.casefold() == str(ref).casefold():
                return info
        raise ClassError(t("No class called {name}.", name=repr(ref)))

    def delete(self, ref: str) -> ClassInfo:
        info = self.find(ref)
        shutil.rmtree(self._dir(info.id))
        return info

    def players(self, ref: str) -> ProfileStore:
        """The class's players, stored like a family's, in the class folder."""
        return ProfileStore(self._dir(self.find(ref).id), pictures=CLASS_PICTURES)

    def update(self, ref: str, **changes: Any) -> ClassInfo:
        """Change settings: roster, names, deleteAtEnd, locked, cub (bools), assigned (ids)
        lang ("en", "sk", or "" for each device's own language), views (["2d", "3d"])
        sounds (["on", "off"]) and themes (["light", "dark"]): both lets each child switch;
        panes (["blocks", "code", "console"]): the panes children may use."""
        info = self.find(ref)
        data = self._read(info.id)
        if changes.get("views") is not None:
            views = changes["views"]
            if not isinstance(views, list) or not views or not set(views) <= set(VIEWS):
                raise ClassError(t("Tick 2D, 3D or both."))
            data["settings"]["views"] = [v for v in VIEWS if v in views]
        if changes.get("sounds") is not None:
            sounds = changes["sounds"]
            if not isinstance(sounds, list) or not sounds or not set(sounds) <= set(SOUNDS):
                raise ClassError(t("Tick On, Off or both."))
            data["settings"]["sounds"] = [v for v in SOUNDS if v in sounds]
        if changes.get("themes") is not None:
            themes = changes["themes"]
            if not isinstance(themes, list) or not themes or not set(themes) <= set(THEMES):
                raise ClassError(t("Tick Light, Dark or both."))
            data["settings"]["themes"] = [v for v in THEMES if v in themes]
        if changes.get("panes") is not None:
            panes = changes["panes"]
            if not isinstance(panes, list) or not panes or not set(panes) <= set(PANES):
                raise ClassError(t("Tick at least one of Blocks, Python and Console."))
            data["settings"]["panes"] = [v for v in PANES if v in panes]
        if changes.get("lang") is not None:
            lang = changes["lang"] or None
            if lang is not None and lang not in LANGS:
                raise ClassError(t("Pick one of these languages: {names}.", names=", ".join(LANGS)))
            data["settings"]["lang"] = lang
        for key in ("roster", "names", "deleteAtEnd", "locked", "cub"):
            if changes.get(key) is not None:
                data["settings"][key] = bool(changes[key])
        if changes.get("assigned") is not None:
            assigned = changes["assigned"]
            if not isinstance(assigned, list) or not all(
                isinstance(i, str) and LEVEL_ID.match(i) for i in assigned
            ):
                raise ClassError(t("Those levels don't look right."))
            data["settings"]["assigned"] = list(dict.fromkeys(assigned))[:500]
        self._write(info.id, data)
        return self._info(data)

    def export(self, ref: str) -> dict[str, Any]:
        """The whole class as one file: every player in the format of ``profile export``."""
        info = self.find(ref)
        data = self._read(info.id)
        store = self.players(info.id)
        return {
            "format": "codezoo-class-export",
            "version": 1,
            "class": {**info.public(), "created": info.created, "settings": info.settings},
            "players": [store.export(p.id) for p in store.profiles()],
            "levels": data["levels"],
        }

    # --- the teacher's own levels ------------------------------------------------

    def levels(self, ref: str) -> dict[str, Level]:
        data = self._read(self.find(ref).id)
        out = {}
        for level_id, entry in data["levels"].items():
            try:
                out[level_id] = Level.from_dict(entry["level"])
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def level_entries(self, ref: str) -> dict[str, Any]:
        return self._read(self.find(ref).id)["levels"]

    def add_level(self, ref: str, level: Any, solution: Any) -> list[str]:
        """Add a level from the editor; checked like ``levels validate`` first.

        Returns the problems found (empty when it was added).
        """
        info = self.find(ref)
        if not isinstance(solution, str):
            return [t("A level needs its solution program.")]
        report = validate_level_data(level, has_solution=True)
        if not report.ok:
            return report.errors
        level_id = level["id"]
        if not isinstance(level_id, str) or not LEVEL_ID.match(level_id):
            return [t("A level id uses only letters, digits, - and _.")]
        try:
            find_level(level_id)
        except LevelError:
            pass
        else:
            return [t("A built-in level already uses the id {id}.", id=level_id)]
        errors = solution_errors(Level.from_dict(level), solution)
        if errors:
            return errors
        data = self._read(info.id)
        if level_id not in data["levels"] and len(data["levels"]) >= MAX_LEVELS:
            return [t("A class can have at most {count} levels.", count=MAX_LEVELS)]
        data["levels"][level_id] = {"level": level, "solution": solution}
        self._write(info.id, data)
        return []

    # --- one player's own settings (over the class's) ------------------------------------

    def player_settings(self, ref: str) -> dict[str, dict[str, Any]]:
        """Per player id: the settings the teacher set for that child only. A missing key
        means "as the class"; "lang": None means "the device's own language"."""
        return dict(self._read(self.find(ref).id).get("playerSettings", {}))

    def set_player_settings(
        self, ref: str, player: str, views: str | None = None, lang: str | None = None
    ) -> dict[str, Any]:
        """``views``: "class", "2d", "3d" or "both"; ``lang``: "class", "device", "en" or
        "sk". None leaves that setting as it is."""
        info = self.find(ref)
        self.players(info.id).find(player)  # the player must be in the class
        data = self._read(info.id)
        every = data.setdefault("playerSettings", {})
        mine = dict(every.get(player, {}))
        if views is not None:
            choices = {"2d": ["2d"], "3d": ["3d"], "both": list(VIEWS)}
            if views == "class":
                mine.pop("views", None)
            elif views in choices:
                mine["views"] = choices[views]
            else:
                raise ClassError(t("Tick 2D, 3D or both."))
        if lang is not None:
            if lang == "class":
                mine.pop("lang", None)
            elif lang == "device" or lang in LANGS:
                mine["lang"] = None if lang == "device" else lang
            else:
                raise ClassError(t("Pick one of these languages: {names}.", names=", ".join(LANGS)))
        if mine:
            every[player] = mine
        else:
            every.pop(player, None)
        self._write(info.id, data)
        return mine

    def forget_player(self, ref: str, player: str) -> None:
        """A removed player's own settings go too."""
        info = self.find(ref)
        data = self._read(info.id)
        if data.get("playerSettings", {}).pop(player, None) is not None:
            self._write(info.id, data)

    def effective(self, ref: str, player: str | None) -> dict[str, Any]:
        """The stage views and language a player's device uses: their own, else the class's."""
        info = self.find(ref)
        public = info.public()
        mine = self.player_settings(info.id).get(player or "", {})
        return {
            "views": mine.get("views", public["views"]),
            "lang": mine["lang"] if "lang" in mine else public["lang"],
        }

    def remove_level(self, ref: str, level_id: str) -> None:
        info = self.find(ref)
        data = self._read(info.id)
        data["levels"].pop(level_id, None)
        data["settings"]["assigned"] = [
            i for i in data["settings"].get("assigned", []) if i != level_id
        ]
        self._write(info.id, data)

    # --- sharing inside the class ------------------------------------------------

    def shares(self, ref: str, status: str | None = None) -> list[dict[str, Any]]:
        items = self._read(self.find(ref).id)["shares"]
        return [s for s in items if status is None or s.get("status") == status]

    def share(self, ref: str, player: str, kind: str, title: Any, payload: Any) -> dict[str, Any]:
        """A child shares a program or a level; classmates see it once the teacher approves."""
        info = self.find(ref)
        profile = self.players(info.id).find(player)
        if kind not in SHARE_KINDS:
            raise ClassError(t("You can share a program or a level."))
        title = " ".join(str(title or "").split())[:MAX_TITLE] or t("Untitled")
        if not isinstance(payload, dict) or len(json.dumps(payload)) > MAX_SHARE_BYTES:
            raise ClassError(t("That is too big to share."))
        if kind == "program" and not (
            isinstance(payload.get("source"), str) and isinstance(payload.get("level"), str)
        ):
            raise ClassError(t("You can share a program or a level."))
        if kind == "level" and not validate_level_data(payload.get("level")).ok:
            raise ClassError(t("That level isn't finished yet: test it in the editor first."))
        if kind == "game":
            _check_game(payload)
        data = self._read(info.id)
        if len(data["shares"]) >= MAX_SHARES:
            raise ClassError(t("The class has shared a lot today! Ask the teacher to tidy up."))
        item = {
            "id": f"s{secrets.token_hex(4)}",
            "player": profile.id,
            "name": profile.name,
            "picture": profile.picture,
            "kind": kind,
            "title": title,
            "payload": payload,
            "status": "pending",
            "created": dt.datetime.now().isoformat(timespec="seconds"),
        }
        data["shares"].append(item)
        self._write(info.id, data)
        return item

    def set_share(self, ref: str, share_id: str, status: str) -> dict[str, Any]:
        """The teacher approves, rejects or deletes a share; a child can report one."""
        if status not in (*SHARE_STATUSES, "deleted"):
            raise ValueError(f"unknown share status {status!r}")
        info = self.find(ref)
        data = self._read(info.id)
        for item in data["shares"]:
            if item["id"] == share_id:
                break
        else:
            raise ClassError(t("That share doesn't exist any more."))
        if status == "deleted":
            data["shares"] = [s for s in data["shares"] if s["id"] != share_id]
        else:
            item["status"] = status
        self._write(info.id, data)
        return item


def _check_game(payload: dict[str, Any]) -> None:
    """A shared game (phase 8): the game itself, its code and its design card."""
    from mse_codezoo.gamemode import GameError, GameSpec  # game mode loads only when used

    if not isinstance(payload.get("source"), str):
        raise ClassError(t("You can share a program or a level."))
    try:
        GameSpec.from_dict(payload.get("game"))
    except (GameError, ValueError):
        raise ClassError(t("That game can't be played yet: press Play first.")) from None
    design = payload.get("design", {})
    if not isinstance(design, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and len(v) <= 300 for k, v in design.items()
    ):
        raise ClassError(t("The design card has too much text."))
