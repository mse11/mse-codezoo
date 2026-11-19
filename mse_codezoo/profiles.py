"""On-device learner profiles, progress, daily time and grown-up settings.

Everything stays in plain JSON files in the user's data folder; nothing leaves the device.
Parent settings live in their own file, so exporting a child's progress never includes them.
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mse_codezoo.i18n import t

PICTURES = ("monkey", "penguin", "beaver", "fox", "octopus", "bee", "turtle", "owl")
MAX_NAME = 24
MAX_SECONDS_PER_TICK = 120
PIN_PATTERN = re.compile(r"^\d{4,8}$")
ID_PATTERN = re.compile(r"^p[0-9a-f]{8}$")
PBKDF2_ROUNDS = 200_000

MISTAKE_KINDS = {
    "bump": "walks into walls or edges",
    "unknown_name": "misspells a command",
    "syntax": "code Python can't read",
    "not_finished": "stops before the goal",
    "too_long": "solves it, but with extra lines",
    "missing_concept": "solves it without the new idea",
    "endless_loop": "loops that never stop",
    "type_mixup": "mixes up numbers, text and yes/no values",
}
ERROR_KINDS = {  # LearnerError.kind (or "syntax") -> mistake kind
    "bump": "bump",
    "unknown_name": "unknown_name",
    "syntax": "syntax",
    "too_many_steps": "endless_loop",
    "type": "type_mixup",
}


class ProfileError(Exception):
    """A request that can't be done, worded for the person using the app."""


class PinError(ProfileError):
    """The grown-up PIN is missing or wrong."""


def default_home() -> Path:
    """Where CodeZoo keeps its files: ``CODEZOO_HOME`` or the OS user-data folder."""
    if env := os.environ.get("CODEZOO_HOME"):
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "CodeZoo"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CodeZoo"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "codezoo"


def today() -> str:
    return dt.date.today().isoformat()


@dataclass
class Profile:
    id: str
    name: str
    picture: str
    created: str


@dataclass
class ParentSettings:
    daily_minutes: int | None = None  # None = no limit
    private_mode: bool = False
    pin_salt: str | None = None
    pin_hash: str | None = None

    @property
    def has_pin(self) -> bool:
        return self.pin_hash is not None

    def public(self) -> dict[str, Any]:
        return {
            "dailyMinutes": self.daily_minutes,
            "privateMode": self.private_mode,
            "hasPin": self.has_pin,
        }


@dataclass
class Attempt:
    """What a finished run tells the progress store."""

    level_id: str
    concepts: list[str]
    solved: bool
    stars: int
    mistakes: list[str] = field(default_factory=list)
    source: str | None = None


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def classify_mistakes(
    solved: bool, stars: list[tuple[bool, str]], error_kind: str | None
) -> list[str]:
    """Turn a run's outcome into mistake kinds for the grown-up report.

    ``error_kind`` is the run's ``LearnerError.kind``, or ``"syntax"`` when Python could
    not read the program, or ``None`` when it ran to the end.
    """
    kinds = []
    if error_kind:
        if error_kind in ERROR_KINDS:
            kinds.append(ERROR_KINDS[error_kind])
    elif not solved:
        kinds.append("not_finished")
    if solved and len(stars) >= 3:
        if not stars[1][0]:
            kinds.append("too_long")
        if not stars[2][0]:
            kinds.append("missing_concept")
    return kinds


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_home()

    # --- files -----------------------------------------------------------------

    def _read(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileError(t("Can't read {name}: {why}", name=path.name, why=exc)) from None

    def _write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic: a crash never leaves half a file

    @property
    def _profiles_path(self) -> Path:
        return self.root / "profiles.json"

    @property
    def _parent_path(self) -> Path:
        return self.root / "parent.json"

    def _progress_path(self, profile_id: str) -> Path:
        if not ID_PATTERN.match(profile_id):
            raise ProfileError(t("That player doesn't exist."))
        return self.root / "progress" / f"{profile_id}.json"

    # --- profiles --------------------------------------------------------------

    def profiles(self) -> list[Profile]:
        data = self._read(self._profiles_path, {"profiles": []})
        return [Profile(**p) for p in data.get("profiles", [])]

    def _save_profiles(self, profiles: list[Profile]) -> None:
        self._write(self._profiles_path, {"profiles": [asdict(p) for p in profiles]})

    def add(self, name: str, picture: str) -> Profile:
        name = " ".join(str(name).split())
        if not name:
            raise ProfileError(t("Please type a name."))
        if len(name) > MAX_NAME:
            raise ProfileError(t("Names can be at most {count} letters long.", count=MAX_NAME))
        if picture not in PICTURES:
            raise ProfileError(t("Pick one of these pictures: {names}.", names=", ".join(PICTURES)))
        profiles = self.profiles()
        if any(p.name.casefold() == name.casefold() for p in profiles):
            raise ProfileError(t("There is already a player called {name}.", name=name))
        profile = Profile(f"p{secrets.token_hex(4)}", name, picture, today())
        self._save_profiles([*profiles, profile])
        return profile

    def find(self, ref: str) -> Profile:
        """A profile by id or by name (any letter case)."""
        for profile in self.profiles():
            if profile.id == ref or profile.name.casefold() == str(ref).casefold():
                return profile
        raise ProfileError(t("No player called {name}.", name=repr(ref)))

    def remove(self, ref: str) -> Profile:
        profile = self.find(ref)
        self._save_profiles([p for p in self.profiles() if p.id != profile.id])
        self._progress_path(profile.id).unlink(missing_ok=True)
        return profile

    # --- progress --------------------------------------------------------------

    def progress(self, ref: str) -> dict[str, Any]:
        profile = self.find(ref)
        data = self._read(self._progress_path(profile.id), {})
        data.setdefault("levels", {})
        data.setdefault("mistakes", {})
        data.setdefault("time", {})
        return data

    def _save_progress(self, profile_id: str, data: dict[str, Any]) -> None:
        self._write(self._progress_path(profile_id), data)

    def record(self, ref: str, attempt: Attempt) -> dict[str, Any]:
        """Store a finished run. Private mode keeps only stars and solved levels."""
        profile = self.find(ref)
        data = self.progress(profile.id)
        private = self.parent().private_mode
        entry = data["levels"].setdefault(attempt.level_id, {"stars": 0, "solved": False})
        entry["concepts"] = attempt.concepts
        if attempt.stars >= entry["stars"]:
            entry["stars"] = attempt.stars
            if attempt.source is not None and not private:
                entry["bestProgram"] = attempt.source
        entry["solved"] = entry["solved"] or attempt.solved
        if not private:
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["lastPlayed"] = today()
            for kind in attempt.mistakes:
                data["mistakes"][kind] = data["mistakes"].get(kind, 0) + 1
        self._save_progress(profile.id, data)
        return entry

    def add_time(self, ref: str, seconds: float) -> dict[str, Any]:
        profile = self.find(ref)
        seconds = max(0.0, min(float(seconds), MAX_SECONDS_PER_TICK))
        data = self.progress(profile.id)
        day = today()
        if self.parent().private_mode:
            data["time"] = {day: data["time"].get(day, 0)}  # today only, for the limit
        data["time"][day] = round(data["time"].get(day, 0) + seconds, 1)
        self._save_progress(profile.id, data)
        return self.today_status(profile.id)

    def today_status(self, ref: str) -> dict[str, Any]:
        data = self.progress(ref)
        minutes = data["time"].get(today(), 0) / 60
        limit = self.parent().daily_minutes
        return {
            "minutesToday": round(minutes, 1),
            "limitMinutes": limit,
            "over": limit is not None and minutes >= limit,
        }

    def export(self, ref: str) -> dict[str, Any]:
        profile = self.find(ref)
        return {
            "format": "codezoo-profile",
            "version": 1,
            "profile": asdict(profile),
            "progress": self.progress(profile.id),
        }

    def import_(self, data: dict[str, Any]) -> Profile:
        if not isinstance(data, dict) or data.get("format") != "codezoo-profile":
            raise ProfileError(t("This is not a CodeZoo profile file."))
        info = data.get("profile") or {}
        progress = data.get("progress") or {}
        name = str(info.get("name", ""))
        if any(p.name.casefold() == name.casefold() for p in self.profiles()):
            name = f"{name} (2)"
        picture = info.get("picture") if info.get("picture") in PICTURES else PICTURES[0]
        profile = self.add(name, picture)
        clean = {key: progress.get(key, {}) for key in ("levels", "mistakes", "time")}
        if not all(isinstance(value, dict) for value in clean.values()):
            self.remove(profile.id)
            raise ProfileError(t("The progress in this file is damaged."))
        self._save_progress(profile.id, clean)
        return profile

    # --- grown-ups ---------------------------------------------------------------

    def parent(self) -> ParentSettings:
        data = self._read(self._parent_path, {})
        known = {
            k: data[k]
            for k in ("daily_minutes", "private_mode", "pin_salt", "pin_hash")
            if k in data
        }
        return ParentSettings(**known)

    def check_pin(self, pin: str | None) -> None:
        settings = self.parent()
        if not settings.has_pin:
            return
        if pin is None or settings.pin_salt is None or settings.pin_hash is None:
            raise PinError(t("This needs the grown-up PIN."))
        if not hmac.compare_digest(_hash_pin(str(pin), settings.pin_salt), settings.pin_hash):
            raise PinError(t("That PIN is not right."))

    def update_parent(
        self,
        *,
        pin: str | None = None,
        daily_minutes: int | None | str = "keep",
        private_mode: bool | None = None,
        new_pin: str | None = None,
        clear_pin: bool = False,
    ) -> ParentSettings:
        """Change grown-up settings. If a PIN is set, ``pin`` must match it."""
        self.check_pin(pin)
        settings = self.parent()
        if daily_minutes != "keep":
            if daily_minutes is not None and (
                isinstance(daily_minutes, bool)
                or not isinstance(daily_minutes, int)
                or not 1 <= daily_minutes <= 600
            ):
                raise ProfileError(t("The daily limit must be between 1 and 600 minutes, or none."))
            settings.daily_minutes = daily_minutes
        if private_mode is not None:
            settings.private_mode = bool(private_mode)
        if clear_pin:
            settings.pin_salt = settings.pin_hash = None
        if new_pin is not None:
            if not PIN_PATTERN.match(str(new_pin)):
                raise ProfileError(t("A PIN is 4 to 8 digits."))
            settings.pin_salt = secrets.token_hex(16)
            settings.pin_hash = _hash_pin(str(new_pin), settings.pin_salt)
        self._write(self._parent_path, asdict(settings))
        return settings

    def report(self, ref: str, levels: list[Any]) -> dict[str, Any]:
        """Concept report for grown-ups: met, practised, mastered; common mistakes; time."""
        profile = self.find(ref)
        data = self.progress(profile.id)
        concepts: dict[str, dict[str, int]] = {}
        for level in levels:
            entry = data["levels"].get(level.id)
            for concept in level.concepts:
                row = concepts.setdefault(
                    concept, {"levels": 0, "tried": 0, "solved": 0, "three": 0}
                )
                row["levels"] += 1
                if entry:
                    row["tried"] += 1
                    row["solved"] += int(entry.get("solved", False))
                    row["three"] += int(entry.get("stars", 0) >= 3)
        rows = []
        for concept, row in sorted(concepts.items()):
            if row["three"] >= min(2, row["levels"]):
                status = "mastered"
            elif row["solved"]:
                status = "practised"
            elif row["tried"]:
                status = "met"
            else:
                status = "not yet"
            rows.append({"concept": concept, "status": status, **row})
        mistakes = sorted(data["mistakes"].items(), key=lambda kv: -kv[1])
        week = [(dt.date.today() - dt.timedelta(days=d)).isoformat() for d in range(7)]
        return {
            "profile": asdict(profile),
            "concepts": rows,
            "mistakes": [
                {"kind": k, "text": t(MISTAKE_KINDS.get(k, k)), "count": n} for k, n in mistakes[:3]
            ],
            "levelsSolved": sum(1 for e in data["levels"].values() if e.get("solved")),
            "stars": sum(e.get("stars", 0) for e in data["levels"].values()),
            "minutesThisWeek": round(sum(data["time"].get(day, 0) for day in week) / 60, 1),
        }
