"""Phase 7: Cub mode (ages 6-8) and read aloud. The cub levels (predict, fix, make), the
per-player switch for grown-ups and teachers, reports and suggestions that keep the two
courses apart, the terminal client, and the web pieces (picture blocks, speech, tints)."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from mse_codezoo.classes import ClassStore
from mse_codezoo.cli import main
from mse_codezoo.game import level_to_json, run_level, solution_errors
from mse_codezoo.hub import Hub
from mse_codezoo.i18n import use_lang
from mse_codezoo.levels import (
    CUB_STEPS,
    find_level,
    is_cub,
    level_files,
    load_level,
    solution_path,
    validate_level_data,
)
from mse_codezoo.profiles import PinError, ProfileStore, sticker_info
from mse_codezoo.server import ApiError, dispatch, list_levels
from mse_codezoo.webbuild import build

LEVELS = [load_level(p) for p in level_files()]
CUBS = [level for level in LEVELS if is_cub(level)]
# the two modules every cub plays (conditions, tricks and story are extras, tested apart)
CORE = [level for level in CUBS if level.module in ("cub-sequences", "cub-loops")]
EXTRAS = [level for level in CUBS if level not in CORE]
WEB = Path(__file__).parents[1] / "mse_codezoo" / "web"


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path)


def solve(store, profile, level):
    source = solution_path(level.path).read_text(encoding="utf-8")
    body = {"level": level.id, "source": source, "profile": profile.id}
    return dispatch("POST", "/api/run", {}, body, store)


# --- the cub levels ---------------------------------------------------------------------------


def test_two_cub_modules_of_ten_levels_in_the_predict_fix_make_pattern():
    modules = {}
    for level in CORE:
        modules.setdefault(level.module, []).append(level)
    assert sorted(modules) == ["cub-loops", "cub-sequences"]
    for levels in modules.values():
        assert len(levels) == 10
        steps = [level.cub for level in levels]
        assert set(steps) == set(CUB_STEPS)
        assert steps[0] == "predict"  # every module starts by watching, not building


def test_cub_levels_are_small_and_use_only_the_first_blocks():
    for level in CORE:
        assert level.mode == "blocks_only", level.id
        assert set(level.unlocked_blocks) <= {
            "step",
            "turn_left",
            "turn_right",
            "grab",
            "for_range",
        }
        rows = level.world["tiles"]
        assert len(rows) <= 4 and all(len(row) <= 6 for row in rows), level.id
        assert not level.variants and not level.signature
        assert level.i18n["sk"]["title"] and len(level.i18n["sk"]["hints"]) == len(level.hints)
        source = solution_path(level.path).read_text(encoding="utf-8")
        assert len(source.strip().splitlines()) <= 7, level.id


def test_every_cub_solution_earns_every_star_for_every_animal():
    for level in CUBS:
        assert solution_errors(level) == [], level.id


def test_fix_levels_start_broken_and_predict_levels_show_their_solution():
    for level in CUBS:
        if level.cub == "fix":
            assert not run_level(level, level.starter).check.solved, level.id
        else:
            assert not level.starter, level.id
        data = level_to_json(level)
        assert data["cub"] == level.cub
        if level.cub == "predict":
            assert data["predict"] == solution_path(level.path).read_text(encoding="utf-8")
        else:
            assert data["predict"] == ""
    # the shown program follows the animal, like every core level
    penguin = level_to_json(find_level("cub2-l01"), "penguin")
    assert penguin["predict"] == level_to_json(find_level("cub2-l01"))["predict"]
    assert "step(1)" in penguin["predict"]


def test_main_course_levels_are_not_cub_levels():
    for level in LEVELS:
        assert (level.cub is not None) == is_cub(level), level.id
    listed = {entry["id"]: entry["cub"] for entry in list_levels()}
    assert listed["cub1-l01"] == "predict" and listed["m01-l01"] is None


def test_validation_of_cub_levels():
    base = json.loads(find_level("cub1-l02").path.read_text(encoding="utf-8"))
    assert validate_level_data(base).errors == []
    errors = lambda **change: validate_level_data({**base, **change}).errors  # noqa: E731
    assert any("cub must be one of" in e for e in errors(cub="watch"))
    assert any('needs "cub"' in e for e in errors(cub=None))
    assert any("module whose name starts" in e for e in errors(module="sequences"))
    assert any("needs a starter" in e for e in errors(cub="fix"))
    assert any("has no starter" in e for e in errors(cub="predict", starter="step(1)\n"))
    main_course = json.loads(find_level("m01-l01").path.read_text(encoding="utf-8"))
    assert validate_level_data(main_course).errors == []


# --- players ---------------------------------------------------------------------------------


def test_a_player_can_start_in_cub_mode_and_a_grown_up_switches_it(store):
    mia = store.add("Mia", "bee", cub=True)
    ema = store.add("Ema", "fox")
    assert mia.cub and not ema.cub
    assert store.find("Mia").cub
    assert dispatch("GET", f"/api/profiles/{mia.id}/progress", {}, {}, store)["cub"] is True
    dispatch("POST", "/api/parent/cub", {}, {"profile": mia.id, "on": False}, store)
    assert not store.find("Mia").cub
    store.update_parent(new_pin="4321")
    with pytest.raises(PinError):
        dispatch("POST", "/api/parent/cub", {}, {"profile": mia.id, "on": True}, store)
    dispatch("POST", "/api/parent/cub", {}, {"pin": "4321", "profile": mia.id, "on": True}, store)
    assert store.find("Mia").cub


def test_the_new_player_form_can_tick_cub_mode(store):
    made = dispatch(
        "POST", "/api/profiles", {}, {"name": "Leo", "picture": "owl", "cub": True}, store
    )
    assert made["cub"] is True
    plain = dispatch(
        "POST", "/api/profiles", {}, {"name": "Ada", "picture": "fox", "cub": "yes"}, store
    )
    assert plain["cub"] is False  # only a real true counts


def test_older_player_files_without_cub_still_load(tmp_path):
    (tmp_path / "profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {"id": "p0000abcd", "name": "Old", "picture": "owl", "created": "2026-01-01"}
                ]
            }
        ),
        encoding="utf-8",
    )
    assert ProfileStore(tmp_path).find("Old").cub is False


def test_export_and_import_keep_cub_mode(store, tmp_path):
    mia = store.add("Mia", "bee", cub=True)
    data = store.export(mia.id)
    assert data["profile"]["cub"] is True
    other = ProfileStore(tmp_path / "home")
    assert other.import_(data).cub is True


def test_the_report_says_when_a_cub_is_ready_for_the_main_course(store):
    mia = store.add("Mia", "bee", cub=True)
    report = store.report(mia.id, LEVELS)
    assert report["cub"] == {"on": True, "solved": 0, "levels": 20, "ready": False}
    concepts = {row["concept"] for row in report["concepts"]}
    assert concepts == {c for level in CUBS for c in level.concepts}  # only the cub ideas
    for level in CUBS:
        solve(store, mia, level)
    report = store.report(mia.id, LEVELS)
    assert report["cub"]["solved"] == 20 and report["cub"]["ready"]
    ema = store.add("Ema", "fox")
    assert not store.report(ema.id, LEVELS)["cub"]["ready"]
    assert "for" in {row["concept"] for row in store.report(ema.id, LEVELS)["concepts"]}
    assert len(store.report(ema.id, LEVELS)["concepts"]) > len(concepts)


def test_finishing_a_cub_module_gives_its_own_sticker(store):
    mia = store.add("Mia", "bee", cub=True)
    stickers = []
    for level in CUBS:
        if level.module == "cub-sequences":
            stickers += solve(store, mia, level)["newStickers"]
    assert {"id": "module:cub-sequences", **sticker_info("module:cub-sequences")} in stickers
    assert sticker_info("module:cub-sequences")["emoji"] == "🐾"
    with use_lang("sk"):
        assert "Mláďatá" in sticker_info("module:cub-loops")["name"]


def test_suggestions_stay_in_the_players_course(store):
    cub_level = find_level("cub2-l04")  # concept "for"
    main_level = find_level("m02-l05")  # also "for"
    mia = store.add("Mia", "bee", cub=True)
    ema = store.add("Ema", "fox")
    for _ in range(3):
        for player, level in ((mia, cub_level), (ema, main_level)):
            body = {"level": level.id, "source": "pass\n", "profile": player.id}
            dispatch("POST", "/api/run", {}, body, store)
    cub_hint = store.suggest(mia.id, cub_level, LEVELS)
    main_hint = store.suggest(ema.id, main_level, LEVELS)
    assert cub_hint and find_level(cub_hint["level"]).module.startswith("cub-")
    assert main_hint and not find_level(main_hint["level"]).module.startswith("cub-")


# --- the classroom hub ------------------------------------------------------------------------


def test_the_teacher_sets_cub_mode_for_the_class_and_per_child(tmp_path):
    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("1.A", "workshop").id)
    head = {"X-Teacher-Token": hub.teacher_token}
    code = {"X-Class-Code": hub.code}
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"cub": True}, head, "t")
    assert overview["class"]["settings"]["cub"] is True
    joined = hub.handle("POST", "/api/class/me", {}, {"picture": "cat"}, code, "c")
    progress = hub.handle("GET", f"/api/profiles/{joined['id']}/progress", {}, {}, code, "c")
    assert progress["cub"] is True
    added = hub.handle(
        "POST",
        "/api/teacher/player",
        {},
        {"name": "Ema", "picture": "dog", "cub": False},
        head,
        "t",
    )
    hub.handle(
        "POST", "/api/teacher/player/cub", {}, {"profile": joined["id"], "on": False}, head, "t"
    )
    players = {
        p["id"]: p["cub"]
        for p in hub.handle("GET", "/api/teacher/overview", {}, {}, head, "t")["players"]
    }
    assert players == {joined["id"]: False, added["id"]: False}
    with pytest.raises(ApiError):  # a child can't switch it
        hub.handle(
            "POST", "/api/teacher/player/cub", {}, {"profile": added["id"], "on": True}, code, "c"
        )


# --- the terminal and the CLI -----------------------------------------------------------------


def test_cli_cub_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["profile", "add", "Mia", "--picture", "bee", "--cub"])
    assert result.exit_code == 0 and "Cub mode" in result.output
    assert "(Cub mode)" in runner.invoke(main, ["profile", "list"]).output
    assert runner.invoke(main, ["profile", "cub", "Mia", "--off"]).exit_code == 0
    assert not ProfileStore(tmp_path).find("Mia").cub
    result = runner.invoke(main, ["play", "--level", "cub1-l01"], input="q\n")
    assert result.exit_code != 0 and "Cub mode level" in result.output


# --- the web client ---------------------------------------------------------------------------


def test_the_page_has_the_cub_pieces():
    index = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="cub-levels"' in index and 'id="new-cub"' in index
    app = (WEB / "app.js").read_text(encoding="utf-8")
    for piece in ("applyCub", "predictGrid", "renderTints", "./speech.js", "describeBlock"):
        assert piece in app
    blocks = (WEB / "blocks.js").read_text(encoding="utf-8")
    assert '"👣 %1"' in blocks and "cz_cub_var" in blocks
    assert 'id="t-cub"' in (WEB / "teacher.html").read_text(encoding="utf-8")


def test_read_aloud_uses_only_the_devices_own_voices():
    speech = (WEB / "speech.js").read_text(encoding="utf-8")
    assert "speechSynthesis" in speech and "localService" in speech
    # nothing is sent anywhere else: the app's own list of recordings (voices/<lang>/
    # manifest.json, next to the page) and the natural voice of its own server on this
    # computer (voice.py: /api/voice, /api/speak), never an address outside it
    assert re.findall(r"fetch\(([^,)]*)", speech) == [
        "`voices/${code}/manifest.json`",
        '"/api/voice"',
        '"/api/speak"',
    ]
    assert "http" not in speech
    look = (WEB / "look.js").read_text(encoding="utf-8")
    assert 'checkbox("read"' in look and "canSpeak" in look


def test_the_offline_build_carries_cub_mode(tmp_path):
    import zipfile

    site = tmp_path / "site"
    build(site)
    assert (site / "speech.js").is_file()
    assert "speech.js" in (site / "sw.js").read_text(encoding="utf-8")  # cached for offline
    with zipfile.ZipFile(site / "engine.zip") as engine:
        assert any("cub1-sequences/l01.json" in name for name in engine.namelist())


def test_the_extra_cub_modules():
    """Conditions (age 7+), the penguin's slide and free story mode: small, in blocks, and
    each lesson module starts by watching (predict)."""
    from mse_codezoo.game import level_to_json, run_level

    modules = {}
    for level in EXTRAS:
        modules.setdefault(level.module, []).append(level)
        assert level.mode == "blocks_only" and len(level.world["tiles"]) <= 4, level.id
        assert level.i18n["sk"]["title"] and len(level.i18n["sk"]["hints"]) == len(level.hints)
        assert solution_errors(level) == [], level.id
        assert level_to_json(level)["coplay"], level.id  # a prompt for the grown-up
    assert sorted(modules) == ["cub-conditions", "cub-story", "cub-tricks"]
    for name in ("cub-conditions", "cub-tricks"):
        steps = [level.cub for level in modules[name]]
        assert steps[0] == "predict" and set(steps) == set(CUB_STEPS), name
    assert {"if", "item_here"} <= set(modules["cub-conditions"][0].unlocked_blocks)
    # story mode: no goal, whatever the child makes counts
    story = modules["cub-story"][0]
    assert story.goal == {"type": "free"}
    run = run_level(story, 'turn_left()\nsay("Hello!")\n')
    assert run.check.solved
    own = level_to_json(story)["coplay"]
    assert own.startswith("Ask the child to tell you the story")


def test_extra_cub_levels_do_not_change_when_a_cub_is_ready(store):
    mia = store.add("Mia", "bee", cub=True)
    for level in CORE:
        solve(store, mia, level)
    report = store.report(mia.id, LEVELS)
    assert report["cub"]["levels"] == 20 and report["cub"]["ready"]
