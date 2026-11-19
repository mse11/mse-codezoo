"""How the animal feels about a run: proud, happy, puzzled, oops, confused or dizzy.

A mistake is never a failure: the animal is puzzled or confused and asks for help, and
every message points at the next thing to try. Clients show the mood as a face and a
short animation; the terminal prints the line. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mse_codezoo.i18n import t

FACES = {
    "proud": "🤩",
    "happy": "😊",
    "puzzled": "🤔",
    "oops": "😵",
    "confused": "😕",
    "dizzy": "😵‍💫",
}


@dataclass
class Feeling:
    mood: str
    text: str

    @property
    def face(self) -> str:
        return FACES[self.mood]

    def to_dict(self) -> dict[str, Any]:
        return {"mood": self.mood, "face": self.face, "text": self.text}


def _pick(options: list[str], seed: int) -> str:
    return options[seed % len(options)]


def feeling(
    *,
    animal: str,
    parsed: bool,
    solved: bool,
    stars: int,
    error_kind: str | None,
    debugging: bool = False,
    seed: int = 0,
) -> Feeling:
    """The mood for a finished run. ``seed`` varies the wording between runs."""
    if not parsed:
        return Feeling(
            "confused",
            t(
                "The {animal} can't read this yet. Look at the line with the red mark.",
                animal=animal,
            ),
        )
    if solved and stars >= 3:
        return Feeling(
            "proud",
            _pick(
                [
                    t("The {animal} is so proud of you! Three stars!", animal=animal),
                    t("Wow! The {animal} does a happy dance. Perfect code!", animal=animal),
                    t("Three stars! You think like a real programmer.", animal=animal),
                ],
                seed,
            ),
        )
    if solved:
        return Feeling(
            "happy",
            t(
                "The {animal} is happy! Can you get every star? Look at the list below.",
                animal=animal,
            ),
        )
    if error_kind == "bump":
        return Feeling(
            "oops",
            _pick(
                [
                    t("Oops! The {animal} rubs its head. Which step went too far?", animal=animal),
                    t(
                        "Ouch! Count the squares again, the {animal} will try once more.",
                        animal=animal,
                    ),
                ],
                seed,
            ),
        )
    if error_kind == "too_many_steps":
        return Feeling(
            "dizzy",
            t(
                "The {animal} went round and round and got dizzy. Does the loop ever stop?",
                animal=animal,
            ),
        )
    if error_kind is not None:
        return Feeling(
            "confused",
            t(
                "The {animal} is confused by one line. "
                "Help it: read the message and fix that line.",
                animal=animal,
            ),
        )
    if debugging:
        return Feeling(
            "puzzled",
            t("The {animal} is puzzled. There is a bug somewhere. Can you find it?", animal=animal),
        )
    return Feeling(
        "puzzled",
        _pick(
            [
                t(
                    "The {animal} wonders what's next. Your program stopped too early.",
                    animal=animal,
                ),
                t("Almost! The {animal} needs a few more commands.", animal=animal),
            ],
            seed,
        ),
    )
