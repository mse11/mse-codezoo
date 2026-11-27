"""Natural voices (voice.py): the optional Piper add-on, without needing it installed."""

import threading
import wave

import pytest

from mse_codezoo import voice
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import CodeZooServer
from tests.test_server import get_json, request


def touch_voice(folder, name, config=True):
    (folder / f"{name}.onnx").write_bytes(b"model")
    if config:
        (folder / f"{name}.onnx.json").write_text("{}")


def test_voice_files_pick_a_voice_per_language(tmp_path):
    touch_voice(tmp_path, "sk_SK-lili-medium")
    touch_voice(tmp_path, "en_US-lessac-medium")
    touch_voice(tmp_path, "en_GB-alan-low")  # a second English voice: the first by name wins
    touch_voice(tmp_path, "de_DE-thorsten-medium", config=False)  # no config: Piper can't use it
    found = voice.voice_files(tmp_path)
    assert sorted(found) == ["en", "sk"]
    assert found["sk"].name == "sk_SK-lili-medium.onnx"
    assert found["en"].name == "en_GB-alan-low.onnx"


def test_no_voices_folder_means_no_voices(tmp_path):
    assert voice.voice_files(tmp_path / "missing") == {}


def test_without_piper_no_language_has_a_natural_voice(monkeypatch, tmp_path):
    touch_voice(tmp_path, "sk_SK-lili-medium")
    monkeypatch.setattr(voice, "voices_dir", lambda: tmp_path)
    monkeypatch.setattr(voice, "piper_installed", lambda: False)
    assert voice.available() == {"engine": None, "langs": [], "voices": {}}
    assert voice.speak_wav("Ahoj", "sk") is None


class FakeVoice:
    """Stands in for a PiperVoice: one short silent sound per call, counted."""

    def __init__(self):
        self.calls = []
        self.paces = []

    def synthesize_wav(self, text, sound, syn_config=None):
        self.calls.append(text)
        self.paces.append(syn_config.length_scale)
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(22050)
        sound.writeframes(b"\0\0" * 100)


@pytest.fixture
def fake_piper(monkeypatch, tmp_path):
    touch_voice(tmp_path, "sk_SK-lili-medium")
    fake = FakeVoice()
    monkeypatch.setattr(voice, "voices_dir", lambda: tmp_path)
    monkeypatch.setattr(voice, "piper_installed", lambda: True)
    monkeypatch.setattr(voice, "_loaded", {"sk": fake})
    monkeypatch.setattr(voice, "_cache", voice.OrderedDict())
    return fake


def test_speak_makes_a_wav_and_remembers_repeated_lines(fake_piper, tmp_path):
    assert voice.available() == {
        "engine": "piper",
        "langs": ["sk"],
        "voices": {"sk": "sk_SK-lili-medium"},
    }
    first = voice.speak_wav("  Mňam!   Ďakujem ", "sk")
    second = voice.speak_wav("Mňam! Ďakujem", "sk")  # same words: from the cache
    assert first == second and first.startswith(b"RIFF")
    assert fake_piper.calls == ["Mňam! Ďakujem."]  # a full stop, so the voice falls at the end
    assert fake_piper.paces == [voice.DEFAULT_PACE]
    (tmp_path / "out.wav").write_bytes(first)
    with wave.open(str(tmp_path / "out.wav")) as sound:
        assert sound.getframerate() == 22050
    assert voice.speak_wav("Hello", "en") is None  # no English voice here
    assert voice.speak_wav("   ", "sk") is None


def test_long_text_is_cut(fake_piper):
    voice.speak_wav("a" * 1000, "sk")
    assert len(fake_piper.calls[0]) == voice.MAX_TEXT + 1  # and ends with a full stop


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("Ahoj", "Ahoj."),
        ("Ahoj!", "Ahoj!"),
        ("Kde si?", "Kde si?"),
        ("Hmm…", "Hmm…"),
        ("x = 3", "x = 3."),
        ("  hello   world  ", "hello world."),
        ("…", "…"),
    ],
)
def test_text_ends_like_a_sentence(text, said):
    assert voice.sentence(text) == said


def test_pace_is_kept_within_limits_and_cached_apart(fake_piper):
    voice.speak_wav("Ahoj", "sk", 1.2)
    voice.speak_wav("Ahoj", "sk", 5)  # far too slow: the slowest allowed
    voice.speak_wav("Ahoj", "sk", 1.2)  # same words and pace: from the cache
    assert fake_piper.paces == [1.2, voice.MAX_PACE]


@pytest.fixture
def server_url(tmp_path_factory):
    store = ProfileStore(tmp_path_factory.mktemp("codezoo-home"))
    server = CodeZooServer("127.0.0.1", 0, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_server_speaks_with_the_natural_voice(fake_piper, server_url):
    status, info = get_json(server_url, "/api/voice")
    assert (
        status == 200 and info["langs"] == ["sk"] and info["voices"] == {"sk": "sk_SK-lili-medium"}
    )
    status, headers, payload = request(server_url, "/api/speak", {"text": "Ahoj!", "lang": "sk"})
    assert status == 200
    assert headers["Content-Type"] == "audio/wav"
    assert payload.startswith(b"RIFF")
    # no voice for the language: 404, and the page uses the device's own voice
    status, answer = get_json(server_url, "/api/speak", {"text": "Hi!", "lang": "en"})
    assert status == 404 and "voice" in answer["error"]
    status, _ = get_json(server_url, "/api/speak", {"text": 5, "lang": "sk"})
    assert status == 400
    status, _ = get_json(server_url, "/api/speak", {"text": "Ahoj", "lang": "sk", "pace": "fast"})
    assert status == 400
    status, _, payload = request(
        server_url, "/api/speak", {"text": "Ahoj", "lang": "sk", "pace": 1.2}
    )
    assert status == 200 and fake_piper.paces[-1] == 1.2
