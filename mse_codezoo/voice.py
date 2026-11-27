"""Natural voices for read aloud and ``say()``, with Piper, when it is installed.

Piper (https://github.com/OHF-Voice/piper1-gpl) is an optional add-on: CodeZoo neither
depends on it nor ships it (it is GPL-3.0; CodeZoo is Apache-2.0). A grown-up installs it
into the same Python and puts voice files in the voices folder::

    uv pip install piper-tts          (or: pip install piper-tts)
    <CodeZoo folder>/voices/sk_SK-lili-medium.onnx  (+ .onnx.json)

Voices come from https://huggingface.co/rhasspy/piper-voices; each has a MODEL_CARD with
its own license. A voice serves the language its file name starts with (``sk_...`` for
Slovak). Without Piper or without a voice for the page's language, the page uses the
device's own speech voice, as before. Nothing leaves the computer: the server makes the
sound itself.
"""

from __future__ import annotations

import io
import threading
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Any

from mse_codezoo.profiles import default_home

MAX_TEXT = 300  # a goal, a hint or a say() line; longer text is cut
# Piper's pace: its ``length_scale`` (1 = the voice's own pace, more = slower). A touch
# slower than the voice's own, so Slovak syllables aren't rushed; the page's "Speaking
# speed" setting sends its own (slow, normal, quick), kept within MIN_PACE..MAX_PACE.
DEFAULT_PACE = 1.05
MIN_PACE, MAX_PACE = 0.7, 1.6
SENTENCE_END = ".!?…:;"
CACHE_SIZE = 64  # a say() in a loop repeats the same words: keep recent sounds

_lock = threading.Lock()
_loaded: dict[str, Any] = {}  # language -> PiperVoice
_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()


def voices_dir() -> Path:
    """Where voice files go: ``voices`` in the CodeZoo folder (shared by every player)."""
    return default_home() / "voices"


def piper_installed() -> bool:
    try:
        import piper  # noqa: F401
    except Exception:  # not installed, or its native parts don't load here
        return False
    return True


def voice_files(folder: Path | None = None) -> dict[str, Path]:
    """Language code -> the voice file for it (the first by name, when there are several)."""
    folder = folder or voices_dir()
    found: dict[str, Path] = {}
    if not folder.is_dir():
        return found
    for model in sorted(folder.glob("*.onnx")):
        if not model.with_suffix(".onnx.json").is_file():
            continue  # Piper needs the voice's config next to it
        lang = model.name.split("_", 1)[0].split("-", 1)[0].lower()
        if lang.isalpha() and len(lang) in (2, 3):
            found.setdefault(lang, model)
    return found


def available() -> dict[str, Any]:
    """What the page needs to know: which languages have a natural voice, and its name
    (the voice file's name without ``.onnx``, shown in the page's tooltips)."""
    if not piper_installed():
        return {"engine": None, "langs": [], "voices": {}}
    files = voice_files()
    return {
        "engine": "piper",
        "langs": sorted(files),
        "voices": {k: p.stem for k, p in files.items()},
    }


def sentence(text: str) -> str:
    """The words on one line, cut to MAX_TEXT, ending like a sentence: Piper lets the voice
    fall at a full stop, so ``say("Ahoj")`` doesn't end hanging in the air."""
    words = " ".join(str(text or "").split())[:MAX_TEXT].rstrip()
    if words and words[-1] not in SENTENCE_END and any(ch.isalnum() for ch in words):
        words += "."
    return words


def speak_wav(text: str, lang: str, pace: float | None = None) -> bytes | None:
    """The words as a WAV sound in the language's voice, or None when there is no voice.
    ``pace`` is Piper's length_scale (more = slower), DEFAULT_PACE when not given."""
    words = sentence(text)
    if not words:
        return None
    pace = DEFAULT_PACE if pace is None else min(MAX_PACE, max(MIN_PACE, float(pace)))
    key = (lang, words, round(pace, 2))
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        voice = _voice(lang)
        if voice is None:
            return None
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as sound:
            voice.synthesize_wav(words, sound, syn_config=_settings(pace))
        audio = buffer.getvalue()
        _cache[key] = audio
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return audio


def _settings(pace: float) -> Any:
    """Piper's synthesis settings with this pace (its length_scale)."""
    try:
        from piper import SynthesisConfig
    except ImportError:  # only in tests, where a stand-in voice takes any settings
        from types import SimpleNamespace

        return SimpleNamespace(length_scale=pace)
    return SynthesisConfig(length_scale=pace)


def _voice(lang: str) -> Any:
    """The loaded voice for a language (loaded once, then kept); call with the lock held."""
    if lang in _loaded:
        return _loaded[lang]
    model = voice_files().get(lang)
    if model is None or not piper_installed():
        return None
    from piper import PiperVoice

    _loaded[lang] = PiperVoice.load(model)
    return _loaded[lang]
