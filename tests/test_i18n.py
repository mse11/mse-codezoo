"""Translations: every message the engine can show exists in Slovak, with the same gaps."""

import ast
import json
import string
from pathlib import Path

import pytest

from mse_codezoo import i18n, scheduler, stdlib, world  # noqa: F401 - their ZooObject kinds
from mse_codezoo.game import level_to_json, run_level
from mse_codezoo.i18n import catalog, from_accept_language, normalize, plural, t, use_lang
from mse_codezoo.interpreter import ZooObject
from mse_codezoo.lang_python import FRIENDLY, parse
from mse_codezoo.levels import find_level, level_files, load_level, load_pack
from mse_codezoo.profiles import MISTAKE_KINDS
from mse_codezoo.versions import NEWER_FEATURES

PACKAGE = Path(i18n.__file__).parent


def message_ids() -> set[str]:
    """Every literal first argument of a ``t(...)`` call, plus texts passed to t() later."""
    ids = set(FRIENDLY.values()) | set(MISTAKE_KINDS.values()) | set(NEWER_FEATURES)
    ids |= {cls.KIND for cls in _all_subclasses(ZooObject)}
    for path in PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            is_t = isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t"
            if is_t and node.args and isinstance(node.args[0], ast.Constant):
                ids.add(node.args[0].value)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Unsupported":
                if node.args and isinstance(node.args[0], ast.Constant):
                    ids.add(node.args[0].value)
    return ids


def _all_subclasses(cls: type) -> set[type]:
    found = set()
    for sub in cls.__subclasses__():
        found |= {sub, *_all_subclasses(sub)}
    return found


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}


SK = catalog("sk")


def test_every_message_has_a_slovak_translation():
    missing = sorted(message_ids() - set(SK))
    assert not missing, f"add these to mse_codezoo/locale/sk.json: {missing}"


def test_no_stale_slovak_messages():
    stale = sorted(set(SK) - message_ids())
    assert not stale, f"no longer used in the code: {stale}"


@pytest.mark.parametrize("message", sorted(SK))
def test_translation_keeps_the_placeholders(message):
    # a translation may drop a name (Slovak avoids gendered verbs) but never invent one;
    # "nouns" (plural for "all the ...") is passed alongside "noun" for languages that need it
    extra = {"nouns"} if "noun" in fields(message) else set()
    assert fields(SK[message]) <= fields(message) | extra, SK[message]


def test_locale_file_is_valid_json_with_a_comment():
    data = json.loads((PACKAGE / "locale" / "sk.json").read_text(encoding="utf-8"))
    assert "_comment" in data


def test_language_follows_the_context():
    assert t("Solved the level") == "Solved the level"
    with use_lang("sk-SK"):
        assert i18n.current() == "sk"
        assert t("Solved the level") == "Level je vyriešený"
        assert t("{max} lines or fewer (used {used})", max=3, used=2).startswith("Najviac 3")
    assert i18n.current() == "en"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("sk", "sk"), ("SK_sk", "sk"), ("en-GB", "en"), ("de", "en"), (None, "en"), ("", "en")],
)
def test_normalize(value, expected):
    assert normalize(value) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("sk-SK,sk;q=0.9,en;q=0.8", "sk"),
        ("en-US,sk;q=0.5", "en"),
        ("de,sk;q=0.5", "sk"),
        ("", "en"),
    ],
)
def test_accept_language(header, expected):
    assert from_accept_language(header) == expected


def test_slovak_plurals():
    forms = {"one": "banán", "few": "banány", "many": "banánov"}
    with use_lang("sk"):
        assert [plural(n, forms) for n in (1, 2, 4, 5, 0)] == [
            "banán",
            "banány",
            "banány",
            "banánov",
            "banánov",
        ]
    assert plural(3, forms) == "banánov"  # English uses "many" for everything but 1


def test_engine_messages_come_in_slovak():
    level = find_level("m01-l03")
    with use_lang("sk"):
        bump = run_level(level, "step(5)\n")
        assert bump.check.message == "Bum! Tu stojí skala, ďalej sa nedá."
        short = run_level(find_level("m02-l01"), "step(1)\ngrab()\n")
        assert short.check.message == "Ešte treba zozbierať: 4 banány."
        assert parse("step(\n").errors[0].message.startswith("Python nevie prečítať riadok 1")


def test_every_level_has_slovak_title_and_hints():
    for path in level_files():
        level = load_level(path)
        sk = level.i18n.get("sk", {})
        assert sk.get("title"), level.id
        assert len(sk.get("hints", [])) == len(level.hints), level.id


def test_level_json_is_translated():
    level = find_level("m05-l02")
    with use_lang("sk"):
        data = level_to_json(level)
    assert data["title"] == "Banán alebo zhnitý banán?"
    assert data["pack"]["animalName"] == "opička"
    assert data["pack"]["itemNames"]["B"] == {"one": "banán", "many": "banány"}
    assert level_to_json(level)["title"] == "Banana or rotten banana?"


def test_programs_see_english_item_names_in_every_language():
    with use_lang("sk"):
        run = run_level(find_level("m05-l02"), 'step(1)\nif item_here() == "banana":\n    grab()\n')
    assert run.check.solved


def test_pack_names_cover_every_item():
    pack = load_pack("monkey")
    for lang in i18n.LANGS:
        assert set(pack.names[lang]["items"]) == set(pack.items), lang
