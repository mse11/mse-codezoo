"""Saved runs (``*.run.json``): one level, one program, every step, small and replayable.

A saved run holds the program's source and IR, the world it started in and every step
with its events, so it replays exactly without running the program again. The storybook
(``story.py``) and ``codezoo replay`` read it. Standard library only.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from mse_codezoo.game import LevelRun, run_to_json, world_to_json
from mse_codezoo.i18n import t
from mse_codezoo.levels import load_pack

RUN_FORMAT = "codezoo-run"
RUN_VERSION = 1
MAX_RUN_STEPS = 20_000


class RunFileError(ValueError):
    """A file that is not a saved CodeZoo run."""


def make_run(run: LevelRun, source: str) -> dict[str, Any]:
    """A run as a saved-run document."""
    spec, _goal = run.level.worlds()[run.variant]
    pack = load_pack(run.animal or run.level.animal)
    return {
        "format": RUN_FORMAT,
        "version": RUN_VERSION,
        "created": dt.date.today().isoformat(),
        "title": run.level.shown_title,
        "source": source,
        "start": world_to_json(spec, pack),
        **run_to_json(run),
    }


def check_run(data: Any) -> dict[str, Any]:
    """The saved run if it looks right; raises ``RunFileError`` otherwise."""
    if not isinstance(data, dict) or data.get("format") != RUN_FORMAT:
        raise RunFileError(t("This is not a saved CodeZoo run."))
    if data.get("version") != RUN_VERSION:
        raise RunFileError(t("This saved run is from another CodeZoo version."))
    start, steps = data.get("start"), data.get("steps")
    if not isinstance(start, dict) or not isinstance(steps, list):
        raise RunFileError(t("This saved run is damaged."))
    if len(steps) > MAX_RUN_STEPS or not all(isinstance(s, dict) for s in steps):
        raise RunFileError(t("This saved run is damaged."))
    for key in ("size", "position", "facing", "items", "walls"):
        if key not in start:
            raise RunFileError(t("This saved run is damaged."))
    return data
