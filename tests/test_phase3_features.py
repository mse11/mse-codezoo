"""Phase 3 features: animal tricks, re-skinned levels, saved runs, storybook, cards with
unlock codes, stickers and habitat, practice suggestions, and their CLI and API."""

import json
import re
import threading
import urllib.request

import pytest
from click.testing import CliRunner

from mse_codezoo import qr
from mse_codezoo.cards import QR_PREFIX, all_cards, card_for_code, cards_html, normalize_code
from mse_codezoo.cli import main
from mse_codezoo.game import level_to_json, reskin_source, run_level
from mse_codezoo.i18n import use_lang
from mse_codezoo.interpreter import LearnerError
from mse_codezoo.levels import (
    animal_names,
    core_animals,
    find_level,
    level_files,
    load_level,
    load_pack,
    validate_level_data,
)
from mse_codezoo.profiles import PRACTICE_AFTER, ProfileError, ProfileStore
from mse_codezoo.runs import RunFileError, check_run, make_run
from mse_codezoo.server import CodeZooServer
from mse_codezoo.story import narrate, storybook_html
from mse_codezoo.world import CrackError, World

LEVELS = [load_level(p) for p in level_files()]


def world(tiles, start=(0, 0, "east"), animal="monkey", **extra):
    return World.from_spec({"tiles": tiles, "start": list(start), **extra}, load_pack(animal))


# --- tricks --------------------------------------------------------------------------


def test_swing_jumps_one_gap():
    w = world([".~."])
    assert w.is_blocked()  # water counts as blocked
    w.swing()
    assert (w.x, w.y) == (2, 0)
    with pytest.raises(LearnerError, match="no gap"):
        w.swing()


def test_water_and_trees_stop_walking():
    with pytest.raises(LearnerError, match="Splash"):
        world([".~"]).step(1)
    with pytest.raises(LearnerError, match="tree"):
        world([".t"]).step(1)


def test_climb_picks_what_grows_on_the_tree():
    w = world([".t"], items=[[1, 0, "C"]])
    assert w.remaining("C") == 1
    w.climb()
    assert w.collected == {"C": 1} and w.remaining("C") == 0


def test_slide_stops_at_rocks_and_cracks_at_thin_ice():
    w = world(["...#"], animal="penguin")
    assert w.slide() == 2 and w.x == 2
    w = world([".-.."], animal="penguin")
    with pytest.raises(LearnerError) as info:
        w.slide()
    assert isinstance(info.value.exception, CrackError)
    assert w.x == 0  # the penguin stopped before the thin ice
    assert "CrackError" in w.actions()


def test_beaver_builds_with_logs_it_carries():
    w = world([".O~."], animal="beaver")
    with pytest.raises(LearnerError, match="no 'oak' log"):
        w.build("oak")
    w.step(1)
    w.grab()
    assert w.inventory() == {"oak": 1}
    w.build("oak")
    assert w.built == {"oak": 1} and w.inventory() == {}
    w.step(2)  # across the new bridge
    assert w.x == 3


def test_fox_sniffs_open_ways_and_must_hide_from_guards():
    w = world(["#.#", ".o.", "#.#"], start=(1, 2, "north"), animal="fox")
    assert w.sniff() == ["ahead"]
    assert w.guard_ahead()
    with pytest.raises(LearnerError, match="guard saw"):
        w.step(1)
    w.hide()
    w.step(1)
    assert w.sniff() == ["left", "ahead", "right"]


def test_each_animal_has_only_its_own_tricks():
    assert "swing" in world(["."]).actions()
    assert "slide" not in world(["."]).actions()
    assert "catch" in world(["."], animal="penguin").actions()
    assert "grab" not in world(["."], animal="penguin").actions()


# --- levels for every animal ---------------------------------------------------------------


def test_core_levels_are_for_every_animal_and_signature_levels_for_one():
    animals = {"monkey", "penguin", "beaver", "fox", "octopus", "bee"}
    assert set(animal_names()) == animals
    signature = [level for level in LEVELS if level.signature]
    assert {level.animal for level in signature} == animals
    for level in LEVELS:
        assert core_animals(level) == ([level.animal] if level.signature else animal_names())


def test_reskin_renames_commands_and_items():
    monkey, penguin = load_pack("monkey"), load_pack("penguin")
    text = reskin_source('grab()\nif item_here() == "banana":\n    say("yum")\n', monkey, penguin)
    assert text == 'catch()\nif item_here() == "fish":\n    say("yum")\n'


def test_a_core_level_is_drawn_for_the_chosen_animal():
    with use_lang("en"):
        data = level_to_json(find_level("m05-l01"), animal="penguin")
    assert data["pack"]["id"] == "penguin"
    assert data["animals"] == animal_names()
    signature = level_to_json(find_level("m08-l02"), animal="monkey")
    assert signature["pack"]["id"] == "penguin"  # a signature level keeps its animal


def test_modules_6_to_10_exist_with_debugging_levels():
    modules = {level.module for level in LEVELS}
    assert {"loops-2", "functions", "errors", "collections", "recursion"} <= modules
    for module in ("loops-2", "functions", "errors", "collections", "recursion"):
        assert any(level.starter for level in LEVELS if level.module == module), module


def test_validation_rejects_tricks_in_a_core_level():
    data = json.loads(level_files()[0].read_text(encoding="utf-8"))
    data["unlockedBlocks"] = [*data["unlockedBlocks"], "swing"]
    assert any("signature" in e for e in validate_level_data(data).errors)


def test_helper_files_come_with_the_level_and_your_own_folder(tmp_path):
    level = find_level("m07-l06")
    program = tmp_path / "prog.py"
    program.write_text("from mine import go\ngo()\n", encoding="utf-8")
    (tmp_path / "mine.py").write_text("def go():\n    grab()\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["run", level.id, str(program)])
    assert "I don't know" not in result.output
    assert run_level(level, "from tricks import hop\nhop(2)\n").result.ok


def test_traceback_lines_are_in_the_run_json(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("def oops():\n    raise ValueError('no')\noops()\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["run", "m01-l01", str(program), "--json"])
    error = json.loads(result.output)["error"]
    assert error["exception"] == "ValueError"
    assert [f["line"] for f in error["traceback"]] == [3, 2]


# --- saved runs and the storybook ------------------------------------------------------------


@pytest.fixture
def saved_run():
    level = find_level("m06-l08")
    source = (level.path.with_name("l08.solution.py")).read_text(encoding="utf-8")
    with use_lang("en"):
        return make_run(run_level(level, source), source)


def test_saved_runs_are_checked(saved_run):
    assert check_run(saved_run) is saved_run
    for broken in ({}, {**saved_run, "version": 9}, {**saved_run, "steps": "x"}):
        with pytest.raises(RunFileError):
            check_run(broken)


def test_narration_tells_the_run_in_order(saved_run):
    sentences = [text for text, _ in narrate(saved_run, load_pack("monkey"))]
    assert sentences[0] == "The monkey took a step."
    assert "It swung across the gap on a vine!" in sentences
    assert "It picked up a banana." in sentences
    assert sentences[-1] == "The end. The monkey did it!"


def test_storybook_is_a_printable_page_with_pictures(saved_run):
    page = storybook_html(saved_run)
    assert page.startswith("<!doctype html>")
    assert page.count("<svg") >= 2
    assert "contenteditable" in page and "print()" in page
    with use_lang("sk"):
        assert "Prehupne sa" in storybook_html(saved_run)


def test_storybook_escapes_what_the_program_said():
    level = find_level("m01-l01")
    source = 'say("<script>alert(1)</script>")\n'
    page = storybook_html(make_run(run_level(level, source), source))
    assert "<script>alert" not in page


# --- cards and QR codes --------------------------------------------------------------------


def test_every_card_has_its_own_code():
    cards = all_cards(LEVELS)
    codes = [card.code for card in cards]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"[A-Z]+-[A-Z]+-\d\d", code) for code in codes)
    assert len({card.animal for card in cards}) == 6


def test_card_codes_forgive_spaces_case_and_the_qr_prefix():
    card = all_cards(LEVELS)[0]
    typed = card.code.lower().replace("-", " ")
    assert normalize_code(typed) == card.code
    assert card_for_code(QR_PREFIX + card.code, LEVELS) == card
    assert card_for_code("NOT-A-CARD", LEVELS) is None


def test_cards_page_has_a_qr_code_per_card():
    page = cards_html("penguin", LEVELS)
    assert page.count('class="card"') == page.count('aria-label="Card code"')
    assert "catch()" in page  # the programs are re-skinned for the penguin


def test_qr_matrix_has_finders_and_the_right_size():
    matrix = qr.encode(QR_PREFIX + "MANGO-TIGER-42")
    assert len(matrix) == 29  # version 3
    for x0, y0 in ((0, 0), (22, 0), (0, 22)):
        ring = [matrix[y0][x0 + i] for i in range(7)]
        assert ring == [True] * 7
    with pytest.raises(ValueError):
        qr.encode("x" * 200)


# --- stickers, habitat, suggestions ------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    store = ProfileStore(tmp_path)
    store.add("Ada", "fox")
    return store


def solve(store, level_id, solved=True, stars=3):
    from mse_codezoo.profiles import Attempt

    level = find_level(level_id)
    store.record("Ada", Attempt(level.id, level.concepts, solved, stars if solved else 0))


def test_stickers_for_first_solve_modules_and_stars(store):
    solve(store, "m01-l01")
    new = store.award("Ada", LEVELS)
    assert [s["id"] for s in new] == ["first:solve"]
    assert store.award("Ada", LEVELS) == []  # never twice
    for level in [lv for lv in LEVELS if lv.module == "sequences"]:
        solve(store, level.id)
    ids = {s["id"] for s in store.award("Ada", LEVELS)}
    assert "module:sequences" in ids and "stars:10" in ids


def test_card_unlock_gives_a_sticker_once(store):
    card = all_cards(LEVELS)[0]
    assert store.unlock_card("Ada", card)["new"] is True
    assert store.unlock_card("Ada", card)["new"] is False
    assert store.stickers("Ada")[0]["id"] == card.sticker


def test_habitat_places_only_earned_stickers_and_outfits_need_stickers(store):
    with pytest.raises(ProfileError):
        store.set_habitat("Ada", outfit="hat")
    solve(store, "m01-l01")
    store.award("Ada", LEVELS)
    habitat = store.set_habitat("Ada", {"first:solve": [10, 80]}, "hat")
    assert habitat["placed"] == {"first:solve": [10.0, 80.0]} and habitat["outfit"] == "hat"
    for bad in ({"stars:100": [1, 1]}, {"first:solve": [200, 1]}, {"first:solve": "x"}):
        with pytest.raises(ProfileError):
            store.set_habitat("Ada", bad)


def test_practice_is_suggested_after_several_failed_tries(store):
    level = find_level("m07-l03")
    for _ in range(PRACTICE_AFTER - 1):
        solve(store, level.id, solved=False)
        assert store.suggest("Ada", level, LEVELS) is None
    solve(store, level.id, solved=False)
    suggestion = store.suggest("Ada", level, LEVELS)
    assert suggestion is not None
    earlier = find_level(suggestion["level"])
    assert set(earlier.concepts) & set(level.concepts)
    assert LEVELS.index(next(lv for lv in LEVELS if lv.id == earlier.id)) < LEVELS.index(
        next(lv for lv in LEVELS if lv.id == level.id)
    )
    solve(store, level.id)
    assert store.suggest("Ada", level, LEVELS) is None


def test_export_and_import_keep_stickers(store, tmp_path):
    solve(store, "m01-l01")
    store.award("Ada", LEVELS)
    other = ProfileStore(tmp_path / "other")
    imported = other.import_(store.export("Ada"))
    assert [s["id"] for s in other.stickers(imported.id)] == ["first:solve"]


# --- CLI ---------------------------------------------------------------------------------


def invoke(*args, **kwargs):
    return CliRunner().invoke(main, [str(a) for a in args], **kwargs)


def test_cli_save_replay_story_and_cards(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("step(4)\ngrab()\n", encoding="utf-8")
    run_file = tmp_path / "r.run.json"
    assert invoke("run", "m01-l01", program, "--save", run_file).exit_code == 0
    replayed = invoke("replay", run_file)
    assert replayed.exit_code == 0 and "collected every banana" in replayed.output
    story = tmp_path / "story.html"
    assert invoke("story", "export", run_file, "-o", story).exit_code == 0
    assert "<svg" in story.read_text(encoding="utf-8")
    cards_file = tmp_path / "cards.html"
    assert invoke("cards", "print", "--animal", "beaver", "-o", cards_file).exit_code == 0
    assert "build(" in cards_file.read_text(encoding="utf-8")
    assert invoke("replay", program).exit_code != 0  # not a saved run


def test_cli_cards_unlock_and_world_new(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path / "home"))
    assert invoke("profile", "add", "Bo").exit_code == 0
    code = all_cards(LEVELS)[0].code
    result = invoke("cards", "unlock", code.lower(), "--profile", "Bo")
    assert result.exit_code == 0 and "codezoo play --level" in result.output
    assert invoke("cards", "unlock", "NOPE-NOPE-11", "--profile", "Bo").exit_code != 0
    content = tmp_path / "content"
    result = invoke("world", "new", "otter", "--content", content)
    assert result.exit_code == 0, result.output
    assert (content / "animals" / "otter" / "SPEC.md").is_file()
    pack = json.loads((content / "animals" / "otter" / "pack.json").read_text(encoding="utf-8"))
    assert pack["actions"]["grab"] == "grab"
    level = json.loads((content / "levels" / "w-otter" / "l01.json").read_text(encoding="utf-8"))
    assert level["animal"] == "otter" and level["signature"] is True
    assert invoke("world", "new", "otter", "--content", content).exit_code != 0
    assert invoke("world", "new", "Bad Name", "--content", content).exit_code != 0


def test_cli_check_tells_about_stickers_and_practice(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path / "home"))
    invoke("profile", "add", "Cy")
    good = tmp_path / "good.py"
    good.write_text("step(4)\ngrab()\n", encoding="utf-8")
    result = invoke("check", "m01-l01", good, "--profile", "Cy")
    assert "New sticker" in result.output
    bad = tmp_path / "bad.py"
    bad.write_text("pass\n", encoding="utf-8")
    for _ in range(PRACTICE_AFTER):
        result = invoke("check", "m07-l03", bad, "--profile", "Cy")
    assert "practice" in result.output


# --- web API -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    store = ProfileStore(tmp_path_factory.mktemp("codezoo-home"))
    server = CodeZooServer("127.0.0.1", 0, store=store)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(base_url, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base_url + path, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def call_json(base_url, path, body=None):
    status, text = call(base_url, path, body)
    return status, json.loads(text)


def test_api_animals_and_signature_flag(base_url):
    status, animals = call_json(base_url, "/api/animals")
    assert status == 200
    assert [a["id"] for a in animals] == animal_names()
    assert next(a for a in animals if a["id"] == "penguin")["actions"]["grab"] == "catch"
    _, levels = call_json(base_url, "/api/levels")
    assert any(level["signature"] for level in levels)


def test_api_run_saves_a_run_and_makes_a_storybook(base_url):
    status, data = call_json(
        base_url, "/api/run", {"level": "m01-l01", "source": "step(4)\ngrab()\n", "save": True}
    )
    assert status == 200 and data["savedRun"]["format"] == "codezoo-run"
    status, story = call_json(base_url, "/api/story", {"run": data["savedRun"]})
    assert status == 200 and "<svg" in story["html"]
    status, _ = call_json(base_url, "/api/story", {"run": {"format": "x"}})
    assert status == 400


def test_api_run_with_own_helper_file_and_another_animal(base_url):
    body = {
        "level": "m01-l01",
        "source": "from mine import go\ngo()\n",
        "modules": {"mine": "def go():\n    step(4)\n    catch()\n"},
        "animal": "penguin",
    }
    status, data = call_json(base_url, "/api/run", body)
    assert status == 200 and data["check"]["solved"] and data["animal"] == "penguin"
    status, _ = call_json(base_url, "/api/run", {**body, "modules": {"bad name": "x"}})
    assert status == 400


def test_api_player_gets_stickers_unlocks_and_a_habitat(base_url):
    _, player = call_json(base_url, "/api/profiles", {"name": "Dee", "picture": "owl"})
    pid = player["id"]
    _, data = call_json(
        base_url, "/api/run", {"level": "m01-l01", "source": "step(4)\ngrab()\n", "profile": pid}
    )
    assert [s["id"] for s in data["newStickers"]] == ["first:solve"]
    assert data["suggestion"] is None
    code = all_cards(LEVELS)[3].code
    status, unlocked = call_json(base_url, f"/api/profiles/{pid}/unlock", {"code": code})
    assert status == 200 and unlocked["new"] and unlocked["card"]["level"]
    status, _ = call_json(base_url, f"/api/profiles/{pid}/unlock", {"code": "NO-NO-10"})
    assert status == 400
    status, habitat = call_json(
        base_url, f"/api/profiles/{pid}/habitat", {"placed": {"first:solve": [50, 50]}}
    )
    assert status == 200 and habitat["placed"]["first:solve"] == [50.0, 50.0]
    _, again = call_json(base_url, f"/api/profiles/{pid}/habitat")
    assert len(again["stickers"]) == 2
    _, progress = call_json(base_url, f"/api/profiles/{pid}/progress")
    assert progress["stickers"] == 2


def test_cards_page_and_editor_check(base_url):
    status, page = call(base_url, "/cards.html?animal=fox")
    assert status == 200 and "<svg" in page
    assert call(base_url, "/cards.html?animal=dragon")[0] == 404
    level = json.loads(level_files()[0].read_text(encoding="utf-8"))
    status, result = call_json(
        base_url, "/api/levels/check", {"level": level, "solution": "step(4)\ngrab()\n"}
    )
    assert status == 200 and result["ok"], result
    _, result = call_json(base_url, "/api/levels/check", {"level": level, "solution": "pass\n"})
    assert not result["ok"] and result["errors"]
    _, result = call_json(
        base_url, "/api/levels/check", {"level": {"id": "x"}, "solution": "pass\n"}
    )
    assert not result["ok"]
    status, data = call_json(
        base_url, "/api/run", {"levelData": level, "source": "step(4)\ngrab()\n"}
    )
    assert status == 200 and data["check"]["solved"]
