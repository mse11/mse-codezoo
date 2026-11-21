"""Pilot readiness (phase 6): opt-in pilot recording, concept checks, export and the report.

Nothing is recorded unless a grown-up (or the teacher, in a class) turns "Take part in a
pilot" on, and never in private mode. Then the progress file of each player gets a
``pilot`` section with what the pilot metrics need (IMPLEMENTATION_PLAN.md, "Pilot
metrics"): when the first level was opened and the first star earned, hints shown before a
level was solved, the concept checks before and after each module, errors the page saw,
and the "would you play again?" smileys.

The export holds a random pilot id per player and an age band, never a name, a picture, a
program or free text. It is a file the grown-up chooses to send; nothing is uploaded.
``report`` merges exported files into the metrics table. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import statistics
from pathlib import Path
from typing import Any

from mse_codezoo.i18n import current, t
from mse_codezoo.profiles import ProfileError, ProfileStore

CHECKS_FILE = Path(__file__).parent / "content" / "checks.json"
AGE_BANDS = ("6-7", "8-9", "10-12", "13-15", "16+", "adult")
AFTER_SHARE = 0.7  # the "after" check is offered once this share of a module's levels is solved
MAX_ERRORS = 1000
SMILEYS = range(1, 6)
ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: easy to read out
EXPORT_FORMAT = "codezoo-pilot"
TARGETS = {  # IMPLEMENTATION_PLAN.md, "Pilot metrics"
    "moduleCompletion": 0.70,
    "medianMinutesToFirstStar": 5.0,
    "solvedBeforeLastHint": 0.60,
    "worstDropOff": 0.15,
    "learningGainShare": 2 / 3,
    "playAgainShare": 0.80,
}


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def enabled(store: ProfileStore) -> bool:
    settings = store.parent()
    return settings.pilot and not settings.private_mode


def section(data: dict[str, Any]) -> dict[str, Any]:
    """The player's pilot data, created on first use (with a random pilot id)."""
    pilot = data.setdefault("pilot", {})
    if "id" not in pilot:
        pilot["id"] = "P-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(6))
    for key in ("opened", "hintsAtSolve", "checks", "smileys"):
        pilot.setdefault(key, {})
    pilot.setdefault("errors", 0)
    return pilot


# --- concept checks -----------------------------------------------------------------------


def load_checks() -> dict[str, list[dict[str, Any]]]:
    return json.loads(CHECKS_FILE.read_text(encoding="utf-8"))["modules"]


def _text(value: dict[str, str]) -> str:
    return value.get(current()) or value.get("en", "")


def questions(module: str) -> list[dict[str, Any]]:
    """A module's questions in the current language, without the answers."""
    out = []
    for q in load_checks().get(module, []):
        out.append(
            {
                "id": q["id"],
                "concept": q["concept"],
                "prompt": _text(q["prompt"]),
                "code": q.get("code"),
                "choices": [
                    {"code": c["code"]} if "code" in c else {"text": _text(c)} for c in q["choices"]
                ],
            }
        )
    return out


def due_check(data: dict[str, Any], module: str, levels: list[Any]) -> str | None:
    """Which check of ``module`` the player should take now: "before", "after" or None."""
    if module not in load_checks():
        return None
    done = data.get("pilot", {}).get("checks", {}).get(module, {})
    if "before" not in done:
        return "before"
    if "after" in done:
        return None
    ids = [lv.id for lv in levels if lv.module == module]
    solved = sum(1 for i in ids if data["levels"].get(i, {}).get("solved"))
    return "after" if ids and solved / len(ids) >= AFTER_SHARE else None


def answer_check(
    store: ProfileStore, ref: str, module: str, phase: str, answers: Any
) -> dict[str, Any]:
    """Store a check; the child sees no score (it isn't a test of them)."""
    if not enabled(store):
        raise ProfileError(t("Pilot recording is off."))
    checks = load_checks()
    if module not in checks or phase not in ("before", "after"):
        raise ProfileError(t("There is no such question set."))
    items = checks[module]
    if not isinstance(answers, list) or len(answers) != len(items):
        raise ProfileError(t("Please answer every question (or skip them all)."))
    profile = store.find(ref)
    data = store.progress(profile.id)
    pilot = section(data)
    skipped = all(a is None for a in answers)
    right = [a == q["answer"] for a, q in zip(answers, items, strict=True)]
    pilot["checks"].setdefault(module, {})[phase] = {
        "date": dt.date.today().isoformat(),
        "skipped": skipped,
        "right": None if skipped else sum(right),
        "of": len(items),
        "concepts": {} if skipped else _by_concept(items, right),
    }
    store._save_progress(profile.id, data)
    return {"ok": True}


def _by_concept(items: list[dict[str, Any]], right: list[bool]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for q, ok in zip(items, right, strict=True):
        row = out.setdefault(q["concept"], [0, 0])
        row[0] += int(ok)
        row[1] += 1
    return out


# --- events from the page and from runs ---------------------------------------------------


def record_open(store: ProfileStore, ref: str, level: Any, levels: list[Any]) -> dict[str, Any]:
    """A level was opened; answers which concept check (if any) is due first."""
    if not enabled(store):
        return {"pilot": False}
    profile = store.find(ref)
    data = store.progress(profile.id)
    pilot = section(data)
    pilot.setdefault("start", now())
    pilot["opened"].setdefault(level.id, now())
    store._save_progress(profile.id, data)
    phase = due_check(data, level.module, levels)
    return {"pilot": True, "check": {"module": level.module, "phase": phase} if phase else None}


def record_run(
    store: ProfileStore, ref: str, level: Any, solved: bool, hints: Any, levels: list[Any]
) -> dict[str, Any] | None:
    """After a run: the first star's time, and hints shown when a level was first solved."""
    if not enabled(store):
        return None
    profile = store.find(ref)
    data = store.progress(profile.id)
    pilot = section(data)
    if solved:
        pilot.setdefault("firstStar", now())
        if level.id not in pilot["hintsAtSolve"]:
            shown = hints if isinstance(hints, int) and not isinstance(hints, bool) else 0
            pilot["hintsAtSolve"][level.id] = [max(0, shown), len(level.hints)]
    store._save_progress(profile.id, data)
    phase = due_check(data, level.module, levels) if solved else None
    return {"module": level.module, "phase": phase} if phase == "after" else None


def record_event(store: ProfileStore, ref: str, kind: Any, value: Any = None) -> dict[str, Any]:
    """Small events from the page: an error it saw, or a smiley (1-5) for today."""
    if not enabled(store):
        return {"pilot": False}
    profile = store.find(ref)
    data = store.progress(profile.id)
    pilot = section(data)
    if kind == "error":
        pilot["errors"] = min(MAX_ERRORS, pilot["errors"] + 1)
    elif kind == "smiley" and value in SMILEYS and not isinstance(value, bool):
        pilot["smileys"][dt.date.today().isoformat()] = value
    else:
        raise ProfileError(t("Unknown pilot event."))
    store._save_progress(profile.id, data)
    return {"pilot": True}


def smiley_due(store: ProfileStore, ref: str) -> bool:
    if not enabled(store):
        return False
    data = store.progress(ref)
    today = dt.date.today().isoformat()
    return today not in data.get("pilot", {}).get("smileys", {})


def set_age_band(store: ProfileStore, ref: str, band: Any) -> dict[str, Any]:
    if band not in (*AGE_BANDS, None, ""):
        raise ProfileError(t("Pick an age band from the list."))
    profile = store.find(ref)
    data = store.progress(profile.id)
    section(data)["ageBand"] = band or None
    store._save_progress(profile.id, data)
    return {"ageBand": band or None, "pilotId": data["pilot"]["id"]}


# --- export and report --------------------------------------------------------------------


def _minutes_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    seconds = (dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)).total_seconds()
    return round(max(0.0, seconds) / 60, 1)


def export(store: ProfileStore, levels: list[Any]) -> dict[str, Any]:
    """Every player's pilot data, anonymised: no names, pictures, programs or free text."""
    modules: dict[str, list[str]] = {}
    for level in levels:
        modules.setdefault(level.module, []).append(level.id)
    players = []
    for profile in store.profiles():
        data = store.progress(profile.id)
        if "pilot" not in data:
            continue
        pilot = section(data)
        entries = data["levels"]
        players.append(
            {
                "pilotId": pilot["id"],
                "ageBand": pilot.get("ageBand"),
                "minutesToFirstStar": _minutes_between(pilot.get("start"), pilot.get("firstStar")),
                "levels": {
                    level_id: {
                        "attempts": entry.get("attempts", 0),
                        "solved": bool(entry.get("solved")),
                        "stars": entry.get("stars", 0),
                    }
                    for level_id, entry in entries.items()
                },
                "opened": sorted(pilot["opened"]),
                "hintsAtSolve": pilot["hintsAtSolve"],
                "modules": {
                    module: {
                        "started": any(i in entries or i in pilot["opened"] for i in ids),
                        "levels": len(ids),
                        "solved": sum(1 for i in ids if entries.get(i, {}).get("solved")),
                    }
                    for module, ids in modules.items()
                    if any(i in entries or i in pilot["opened"] for i in ids)
                },
                "checks": pilot["checks"],
                "errors": pilot["errors"],
                "smileys": sorted(pilot["smileys"].values()),
                "mistakes": dict(data.get("mistakes", {})),
            }
        )
    return {
        "format": EXPORT_FORMAT,
        "version": 1,
        "exported": dt.date.today().isoformat(),
        "players": players,
    }


def describe_export(data: dict[str, Any]) -> list[str]:
    """What is in an export, in words, for the consent screen."""
    return [
        t(
            "{count} player(s), each with a random pilot id and an age band",
            count=len(data["players"]),
        ),
        t("per level: tries, solved or not, stars, and hints used before solving"),
        t("the questions before and after each module: how many were right"),
        t("minutes to the first star, errors the page saw, and the smileys"),
        t("no names, no pictures, no programs, nothing typed"),
    ]


def report(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge exported files into the pilot metrics, each with its target."""
    players: dict[str, dict[str, Any]] = {}
    for data in files:
        if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
            raise ValueError("not a CodeZoo pilot export")
        for player in data.get("players", []):
            players[player["pilotId"]] = player  # a newer export of the same player wins
    started = completed = 0
    first_star = []
    hint_levels = before_last = 0
    reached: dict[str, list[int]] = {}
    gains = gain_players = 0
    happy = smileys = 0
    errors = 0
    for player in players.values():
        for module in player.get("modules", {}).values():
            if module["started"]:
                started += 1
                completed += int(module["solved"] >= module["levels"])
        if player.get("minutesToFirstStar") is not None:
            first_star.append(player["minutesToFirstStar"])
        for shown, total in player.get("hintsAtSolve", {}).values():
            if total:
                hint_levels += 1
                before_last += int(shown < total)
        seen = set(player.get("opened", [])) | set(player.get("levels", {}))
        for level_id in seen:
            row = reached.setdefault(level_id, [0, 0])
            row[0] += 1
            row[1] += int(player.get("levels", {}).get(level_id, {}).get("solved", False))
        for check in player.get("checks", {}).values():
            before, after = check.get("before"), check.get("after")
            if before and after and not before.get("skipped") and not after.get("skipped"):
                gain_players += 1
                gains += int(after["right"] > before["right"])
        for value in player.get("smileys", []):
            smileys += 1
            happy += int(value >= 4)
        errors += player.get("errors", 0)
    drop = {lid: (n - s) / n for lid, (n, s) in reached.items() if n}
    worst = max(drop.items(), key=lambda kv: kv[1], default=(None, None))
    values = {
        "moduleCompletion": completed / started if started else None,
        "medianMinutesToFirstStar": statistics.median(first_star) if first_star else None,
        "solvedBeforeLastHint": before_last / hint_levels if hint_levels else None,
        "worstDropOff": worst[1],
        "learningGainShare": gains / gain_players if gain_players else None,
        "playAgainShare": happy / smileys if smileys else None,
    }
    lower_is_better = {"medianMinutesToFirstStar", "worstDropOff"}
    metrics = []
    for key, value in values.items():
        target = TARGETS[key]
        if value is None:
            met = None
        else:
            met = value <= target if key in lower_is_better else value >= target
        metrics.append({"metric": key, "value": value, "target": target, "met": met})
    return {
        "players": len(players),
        "metrics": metrics,
        "worstLevel": worst[0],
        "errors": errors,
        "checkPairs": gain_players,
    }
