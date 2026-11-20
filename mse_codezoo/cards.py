"""Printable unplugged cards: act out a level on the floor, then unlock it on the screen.

Each card shows one level's world and a program to act out (one child is the animal,
another reads the program). The card carries a short word code (``MANGO-TIGER-42``) and
the same code as a QR code; typing or scanning it unlocks a sticker and opens the level.
Nothing is bought and nothing leaves the device. Standard library only.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any

from mse_codezoo import qr
from mse_codezoo.game import reskin_source, world_to_json
from mse_codezoo.i18n import current, t
from mse_codezoo.levels import Level, animal_names, core_animals, load_pack, solution_path
from mse_codezoo.profiles import module_name
from mse_codezoo.story import picture

QR_PREFIX = "codezoo:card:"
WORDS = (
    "MANGO",
    "TIGER",
    "LEMON",
    "OTTER",
    "PANDA",
    "ZEBRA",
    "CAMEL",
    "KOALA",
    "LLAMA",
    "MOOSE",
    "BERRY",
    "CLOUD",
    "RIVER",
    "STONE",
    "MAPLE",
    "OLIVE",
    "PEACH",
    "TULIP",
    "ACORN",
    "CORAL",
    "DAISY",
    "FERN",
    "HONEY",
    "IGLOO",
    "JELLY",
    "KIWI",
    "LOTUS",
    "MELON",
    "NUTMEG",
    "ORBIT",
    "PEARL",
    "QUAIL",
)
CODE_PATTERN = re.compile(r"[A-Z]+-[A-Z]+-\d{2}")


@dataclass(frozen=True)
class Card:
    id: str  # "monkey-loops-1"
    animal: str
    module: str
    level_id: str
    code: str

    @property
    def sticker(self) -> str:
        return f"card:{self.id}"


def code_for(card_id: str) -> str:
    digest = hashlib.sha256(card_id.encode()).digest()
    first, second = WORDS[digest[0] % len(WORDS)], WORDS[digest[1] % len(WORDS)]
    return f"{first}-{second}-{digest[2] % 90 + 10}"


def normalize_code(text: str) -> str:
    """What the child typed or scanned, as a card code: spaces and case don't matter."""
    text = str(text).strip()
    if text.lower().startswith(QR_PREFIX):
        text = text[len(QR_PREFIX) :]
    words = re.findall(r"[A-Za-z]+|\d+", text)
    return "-".join(words).upper()


def cards_for(animal: str, levels: list[Level]) -> list[Card]:
    """One card per module: the animal's own level there if it has one, else the first."""
    by_module: dict[str, Level] = {}
    for level in levels:
        if animal not in core_animals(level):
            continue
        chosen = by_module.get(level.module)
        if chosen is None or (level.signature and not chosen.signature):
            by_module[level.module] = level
    cards = []
    for module, level in by_module.items():
        card_id = f"{animal}-{module}"
        cards.append(Card(card_id, animal, module, level.id, code_for(card_id)))
    return cards


def all_cards(levels: list[Level]) -> list[Card]:
    return [card for animal in animal_names() for card in cards_for(animal, levels)]


def card_for_code(code: str, levels: list[Level]) -> Card | None:
    wanted = normalize_code(code)
    return next((card for card in all_cards(levels) if card.code == wanted), None)


STYLE = """
:root { color-scheme: light; }
body { font: 15px/1.4 "Segoe UI", system-ui, sans-serif; margin: 0; background: #f4f1e8;
  color: #2b2620; }
main { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px; padding: 16px; max-width: 1100px; margin: 0 auto; }
header { max-width: 1100px; margin: 0 auto; padding: 16px 16px 0; }
.card { background: #fff; border: 2px dashed #c9bda8; border-radius: 16px; padding: 14px;
  break-inside: avoid; page-break-inside: avoid; display: flex; flex-direction: column;
  gap: 8px; }
.card h2 { margin: 0; font-size: 20px; }
.card .module { color: #7a6f60; font-size: 13px; text-transform: uppercase;
  letter-spacing: .04em; }
.card svg { max-width: 100%; height: auto; }
.card pre { background: #f6f1e3; border-radius: 8px; padding: 8px; margin: 0;
  font-size: 14px; white-space: pre-wrap; }
.unlock { display: flex; align-items: center; gap: 12px; margin-top: auto; }
.unlock code { font-size: 18px; font-weight: 700; letter-spacing: .06em; }
button { font: inherit; padding: 8px 18px; border-radius: 999px; border: 0;
  background: #f2b84b; cursor: pointer; }
@media print { button { display: none; } body { background: #fff; }
  main { grid-template-columns: 1fr 1fr; } }
"""


def card_html(card: Card, level: Level) -> str:
    pack = load_pack(card.animal)
    spec, _goal = level.worlds()[0]
    start = world_to_json(spec, pack)
    source = ""
    if level.path is not None and solution_path(level.path).is_file():
        source = solution_path(level.path).read_text(encoding="utf-8")
        source = reskin_source(source, load_pack(level.animal), pack)
    module = module_name(level.module)
    steps = t(
        "Act it out: make a {width} × {height} grid on the floor. One of you is the {animal}; "
        "the other reads the program aloud, one line at a time.",
        width=start["size"][0],
        height=start["size"][1],
        animal=pack.animal_name(),
    )
    return "".join(
        [
            '<article class="card">',
            f'<div class="module">{html.escape(pack.emoji)} {html.escape(module)}</div>',
            f"<h2>{html.escape(level.shown_title)}</h2>",
            picture(start, [], pack),
            f"<p>{html.escape(steps)}</p>",
            f"<pre>{html.escape(source.strip())}</pre>" if source.strip() else "",
            '<div class="unlock">',
            qr.svg(QR_PREFIX + card.code, module=3, label=html.escape(t("Card code"))),
            f"<div>{html.escape(t('Then type this code in CodeZoo:'))}<br>"
            f"<code>{html.escape(card.code)}</code></div>",
            "</div></article>",
        ]
    )


def cards_html(animal: str, levels: list[Level]) -> str:
    pack = load_pack(animal)
    by_id = {level.id: level for level in levels}
    cards = cards_for(animal, levels)
    title = t("CodeZoo cards: {animal}", animal=pack.animal_name())
    body = [card_html(card, by_id[card.level_id]) for card in cards]
    return (
        f'<!doctype html><html lang="{current()}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>"
        f"<header><h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(t('Cut out the cards. Play each one away from the screen first.'))}</p>"
        f'<button onclick="print()">{html.escape(t("Print the cards"))}</button></header>'
        f"<main>{''.join(body)}</main></body></html>\n"
    )


def card_public(card: Card, levels: list[Level]) -> dict[str, Any]:
    level = next(level for level in levels if level.id == card.level_id)
    return {
        "id": card.id,
        "animal": card.animal,
        "module": card.module,
        "level": card.level_id,
        "title": level.shown_title,
        "sticker": card.sticker,
    }
