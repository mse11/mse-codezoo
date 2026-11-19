"""Translations for messages the engine shows to learners and grown-ups.

Messages are written in English in the code and wrapped in ``t()``; the English text is
the key. Other languages live in ``mse_codezoo/locale/<lang>.json`` as
``{"English template": "translated template"}``. Placeholders use ``str.format`` names,
so literal braces in a template that has placeholders are written ``{{`` and ``}}``.

The current language is a context variable, so each web request (each thread) can use
its own. Python keywords and command names (``for``, ``step``) are never translated.
Standard library only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from pathlib import Path
from typing import Any

LANGS = ("en", "sk")
DEFAULT_LANG = "en"
LOCALE_DIR = Path(__file__).parent / "locale"

_current: ContextVar[str] = ContextVar("codezoo_lang", default=DEFAULT_LANG)


def normalize(lang: str | None) -> str:
    """``"sk-SK"`` -> ``"sk"``; anything unknown -> English."""
    if not lang:
        return DEFAULT_LANG
    code = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGS else DEFAULT_LANG


def from_accept_language(header: str | None) -> str:
    """Pick a language from an HTTP ``Accept-Language`` header."""
    for part in (header or "").split(","):
        code = normalize(part.split(";")[0])
        if code != DEFAULT_LANG or part.strip().lower().startswith("en"):
            return code
    return DEFAULT_LANG


def current() -> str:
    return _current.get()


@contextmanager
def use_lang(lang: str | None) -> Iterator[str]:
    token = _current.set(normalize(lang))
    try:
        yield _current.get()
    finally:
        _current.reset(token)


@cache
def catalog(lang: str) -> dict[str, str]:
    if lang == DEFAULT_LANG:
        return {}
    path = LOCALE_DIR / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {key: value for key, value in data.items() if not key.startswith("_")}


def t(message: str, /, **values: Any) -> str:
    """``message`` in the current language, with ``{placeholders}`` filled in."""
    template = catalog(current()).get(message, message)
    return template.format(**values) if values else template


def plural(n: int, forms: dict[str, str] | str) -> str:
    """Pick the right noun form for ``n`` in the current language.

    ``forms`` has ``one`` and ``many`` (English) plus ``few`` (Slovak: 2 to 4).
    A plain string is used as it is.
    """
    if isinstance(forms, str):
        return forms
    if n == 1:
        return forms.get("one") or forms.get("many", "")
    if current() == "sk" and 2 <= n <= 4:
        return forms.get("few") or forms.get("many", "")
    return forms.get("many") or forms.get("one", "")
