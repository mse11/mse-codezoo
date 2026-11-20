"""Storybook: a saved run turned into picture pages a child and a grown-up can finish.

The narration is generated from the run's events ("The monkey took 3 steps and found a
banana"); each page has a picture of the world at that moment. The page is plain HTML:
the title and one line per page can be typed into, and it prints on paper or to PDF.
Nothing is sent anywhere. Standard library only.
"""

from __future__ import annotations

import html
from typing import Any

from mse_codezoo.i18n import current, t
from mse_codezoo.levels import LevelError, load_pack
from mse_codezoo.runs import check_run
from mse_codezoo.term import StageState
from mse_codezoo.world import CLOCKWISE, Pack

CELL = 40
SENTENCES_PER_PAGE = 3
MAX_PAGES = 12
ITEM_EMOJI = {
    "banana": "🍌",
    "coconut": "🥥",
    "rotten": "🤢",
    "fish": "🐟",
    "pebble": "🪨",
    "crab": "🦀",
    "stick": "🥢",
    "leaf": "🍃",
    "thorn": "🌵",
    "oak": "🪵",
    "pine": "🌲",
    "birch": "🌳",
    "berry": "🫐",
    "mushroom": "🍄",
    "trap": "🪤",
    "egg": "🥚",
}
TERRAIN_STYLE = {
    "~": ("#7cc4f0", ""),
    "t": ("#cfe8c0", "🌴"),
    "-": ("#e8f4fb", "〰"),
    "o": ("#fde2e2", "👁"),
    "=": ("#c79a6b", ""),
}


def narrate(data: dict[str, Any], pack: Pack) -> list[tuple[str, list[dict[str, Any]]]]:
    """(sentence, events up to and including it) for every story beat of a run."""
    animal = pack.animal_name()
    beats: list[tuple[str, list[dict[str, Any]]]] = []
    events = [e for step in data["steps"] for e in step.get("events", [])]
    facing = data["start"]["facing"]
    done: list[dict[str, Any]] = []
    i = 0
    while i < len(events):
        event = events[i]
        kind = event["type"]
        if kind == "move":
            sliding = bool(event.get("slide"))
            j = i
            while (
                j < len(events)
                and events[j]["type"] == "move"
                and bool(events[j].get("slide")) == sliding
            ):
                j += 1
            count = j - i
            done += events[i:j]
            if sliding:
                text = t(
                    "The {animal} slid across the ice ({count} squares).",
                    animal=animal,
                    count=count,
                )
            elif count == 1:
                text = t("The {animal} took a step.", animal=animal)
            else:
                text = t("The {animal} took {count} steps.", animal=animal, count=count)
            beats.append((text, list(done)))
            i = j
            continue
        done.append(event)
        text = None
        match kind:
            case "turn":
                before = CLOCKWISE.index(facing)
                facing = event["facing"]
                left = (before - 1) % 4 == CLOCKWISE.index(facing)
                text = t("It turned left.") if left else t("It turned right.")
            case "grab" if event.get("item"):
                text = t("It picked up a {noun}.", noun=pack.noun(event["item"]))
            case "grab":
                text = t("It reached down, but nothing was there.")
            case "say":
                text = t('It said "{text}".', text=event["text"])
            case "bump":
                text = t("Bump! Something was in the way.")
            case "swing":
                text = t("It swung across the gap on a vine!")
            case "climb" if event.get("item"):
                text = t("It climbed a tree and picked a {noun}.", noun=pack.noun(event["item"]))
            case "climb":
                text = t("It climbed a tree, but found nothing.")
            case "crack":
                text = t("Crack! The ice was too thin there.")
            case "build":
                text = t("It built a {noun} into the dam.", noun=pack.noun(event["item"]))
            case "hide":
                text = t("It hid, quiet as a mouse.")
            case "call" if event.get("depth") == 1:
                text = t("It used its trick `{name}`.", name=event["name"])
        if text:
            beats.append((text, list(done)))
        i += 1
    solved = bool(data.get("check", {}).get("solved"))
    end = (
        t("The end. The {animal} did it!", animal=animal)
        if solved
        else t("The end... for now. Next time it will work!")
    )
    beats.append((end, list(done)))
    return [(text[:1].upper() + text[1:], events) for text, events in beats]


def pages(beats: list[tuple[str, list[dict[str, Any]]]]) -> list[tuple[list[str], int]]:
    """Group the beats into pages: (sentences, how many events have happened by then)."""
    per_page = max(SENTENCES_PER_PAGE, -(-len(beats) // MAX_PAGES))
    out = []
    for start in range(0, len(beats), per_page):
        chunk = beats[start : start + per_page]
        out.append(([text for text, _ in chunk], len(chunk[-1][1])))
    return out


def picture(start: dict[str, Any], events: list[dict[str, Any]], pack: Pack) -> str:
    """The world after ``events``, as an inline SVG."""
    state = StageState.from_json(start)
    for event in events:
        state.apply(event)
    width, height = state.width * CELL, state.height * CELL
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="{html.escape(t("The world"))}">',
        f'<rect width="{width}" height="{height}" fill="#f3ecd6"/>',
    ]
    half = CELL / 2

    def cell(x: int, y: int, fill: str) -> None:
        parts.append(
            f'<rect x="{x * CELL + 1}" y="{y * CELL + 1}" width="{CELL - 2}" '
            f'height="{CELL - 2}" rx="5" fill="{fill}"/>'
        )

    def emoji(x: int, y: int, text: str, size: int = 24) -> None:
        parts.append(
            f'<text x="{x * CELL + half}" y="{y * CELL + half + 1}" font-size="{size}" '
            f'text-anchor="middle" dominant-baseline="central">{html.escape(text)}</text>'
        )

    for (x, y), kind in sorted(state.terrain.items()):
        fill, mark = TERRAIN_STYLE.get(kind, ("#ddd", ""))
        cell(x, y, fill)
        if mark:
            emoji(x, y, mark, 22)
    for x, y in sorted(state.walls):
        cell(x, y, "#8a8178")
    for (x, y), tile in sorted(state.items.items()):
        emoji(x, y, ITEM_EMOJI.get(pack.item_name(tile), "⭐"))
    px, py = state.position
    emoji(px, py, pack.emoji or "🐾", 30)
    if state.bubble:
        parts.append(
            f'<text x="{px * CELL + half}" y="{max(py * CELL - 4, 12)}" font-size="13" '
            f'text-anchor="middle">{html.escape(state.bubble[:40])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


STYLE = """
:root { color-scheme: light; }
body { font: 18px/1.5 "Segoe UI", system-ui, sans-serif; margin: 0; background: #faf6ea;
  color: #2b2620; }
main { max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 34px; margin: 8px 0 4px; }
.cover p { color: #6b6257; margin: 0 0 24px; }
.page { background: #fff; border-radius: 14px; padding: 20px; margin: 0 0 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.12); break-inside: avoid; page-break-inside: avoid; }
.page svg { max-width: 100%; height: auto; display: block; margin: 0 auto 12px; }
.page .number { float: right; color: #9a8f80; font-size: 14px; }
.own { border-bottom: 2px dashed #c9bda8; min-height: 1.6em; color: #3a6ea5; }
.own:empty::before { content: attr(data-placeholder); color: #b5a994; }
[contenteditable]:focus { outline: 2px solid #f2b84b; border-radius: 4px; }
button { font: inherit; padding: 8px 18px; border-radius: 999px; border: 0;
  background: #f2b84b; cursor: pointer; }
pre { background: #f6f1e3; padding: 12px; border-radius: 10px; overflow-x: auto;
  font-size: 15px; }
@media print { button, .noprint { display: none; } body { background: #fff; }
  .page { box-shadow: none; border: 1px solid #ddd; } }
"""


def storybook_html(data: dict[str, Any]) -> str:
    """A printable storybook for a saved run."""
    data = check_run(data)
    try:
        pack = load_pack(str(data.get("animal") or "monkey"))
    except LevelError:
        pack = load_pack("monkey")
    animal = pack.animal_name()
    beats = narrate(data, pack)
    events = [e for step in data["steps"] for e in step.get("events", [])]
    title = t(
        "The {animal}'s adventure: {level}",
        animal=animal,
        level=str(data.get("title") or data.get("level", "")),
    )
    placeholder = t("Your line for this page...")
    intro = t("A CodeZoo story. Tap the title or the dashed lines to write your own.")
    body = [
        '<section class="cover">',
        f"<h1 contenteditable>{html.escape(title)}</h1>",
        f"<p>{html.escape(intro)}</p>",
        f'<button onclick="print()">{html.escape(t("Print the storybook"))}</button>',
        "</section>",
    ]
    for number, (sentences, upto) in enumerate(pages(beats), 1):
        body += [
            '<section class="page">',
            f'<span class="number">{number}</span>',
            picture(data["start"], events[:upto], pack),
            *[f"<p>{html.escape(text)}</p>" for text in sentences],
            f'<p class="own" contenteditable data-placeholder="{html.escape(placeholder)}"></p>',
            "</section>",
        ]
    source = str(data.get("source") or "")
    if source.strip():
        body += [
            '<section class="page">',
            f"<p>{html.escape(t('The program that told the story:'))}</p>",
            f"<pre>{html.escape(source)}</pre>",
            "</section>",
        ]
    return (
        f'<!doctype html><html lang="{current()}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
        f"<body><main>{''.join(body)}</main></body></html>\n"
    )
