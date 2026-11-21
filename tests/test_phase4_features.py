"""Phase 4 features: octopus and bee, new goals, release islands, the server's dispatch,
the graduation and offline-build commands."""

import json
import zipfile

import pytest
from click.testing import CliRunner

from mse_codezoo import interpreter, versions
from mse_codezoo.cli import main
from mse_codezoo.game import lock_reason, run_level, solution_errors
from mse_codezoo.goals import goal_errors, goal_met
from mse_codezoo.lang_python import parse
from mse_codezoo.levels import Level, find_level, level_files, load_level, load_pack
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import dispatch, dispatch_json
from mse_codezoo.world import World

LEVELS = [load_level(p) for p in level_files()]
REEF = {"tiles": ["..B..", ".....", "B...B", ".....", "..B.."], "start": [2, 2, "north"]}


def run_in(spec, source, animal="monkey", **kwargs):
    world = World.from_spec(spec, load_pack(animal))
    result = interpreter.run(parse(source).program, world=world, **kwargs)
    world.printed = result.output
    return world, result


def test_modules_eleven_to_fifteen_and_the_islands_ship():
    ids = [level.id for level in LEVELS]
    for module in ("m11", "m12", "m13", "m14", "m15"):
        assert sum(i.startswith(f"{module}-") for i in ids) >= 6
    for island in ("i310", "i312", "i313", "i314", "i315"):
        assert any(i.startswith(f"{island}-") for i in ids)
    assert {lvl.animal for lvl in LEVELS if lvl.signature} >= {"octopus", "bee"}


def test_octopus_arms_work_at_the_same_time():
    source = (
        "import asyncio\nasync def main():\n"
        "    await asyncio.gather(reach(0), reach(2), reach(4), reach(6))\nasyncio.run(main())\n"
    )
    world, result = run_in(REEF, source, "octopus")
    assert result.error is None
    assert world.remaining() == 0 and world.elapsed == 4
    one_by_one = source.replace(
        "await asyncio.gather(reach(0), reach(2), reach(4), reach(6))",
        "for arm in (0, 2, 4, 6):\n        await reach(arm)",
    )
    world, _ = run_in(REEF, one_by_one, "octopus")
    assert world.remaining() == 0 and world.elapsed == 16


def test_reach_without_await_does_nothing_and_says_why():
    level = Level.from_dict(
        {
            "id": "t-l01",
            "module": "test",
            "concepts": [],
            "animal": "octopus",
            "signature": True,
            "world": REEF,
            "goal": {"type": "collect_all", "item": "B"},
        }
    )
    run = run_level(level, "reach(0)\n")
    assert not run.check.solved
    assert "await reach(3)" in run.check.message


def test_octopus_arm_numbers_are_checked():
    _, result = run_in(
        REEF, "import asyncio\nasync def m():\n    await reach(9)\nasyncio.run(m())\n", "octopus"
    )
    assert "arms 0 to 7" in result.error.message


def test_stretch_in_threads_and_the_gil():
    source = (
        "import threading\ndef gather(arm):\n    for _ in range(3):\n        x = arm\n"
        "    stretch(arm)\n"
        "ts = [threading.Thread(target=gather, args=(a,)) for a in (0, 2, 4, 6)]\n"
        "for t in ts:\n    t.start()\nfor t in ts:\n    t.join()\n"
    )
    with_gil, _ = run_in(REEF, source, "octopus")
    without, _ = run_in({**REEF, "gil": False}, source, "octopus")
    assert with_gil.remaining() == 0 and without.remaining() == 0
    assert without.elapsed < with_gil.elapsed


def test_bee_flies_over_rocks_but_must_land():
    world, result = run_in({"tiles": [".#B"], "start": [0, 0, "east"]}, "fly(2)\ngrab()\n", "bee")
    assert result.error is None and world.remaining() == 0
    _, result = run_in({"tiles": [".B#"], "start": [0, 0, "east"]}, "fly(2)\n", "bee")
    assert "nowhere to land" in result.error.message


def test_print_time_and_file_goals():
    world, _ = run_in(
        {"tiles": ["."], "start": [0, 0, "east"], "inputs": ["Bea"], "data": {"a.txt": "x"}},
        "name = input()\nprint(name)\nwith open('a.txt', 'a') as f:\n    f.write('y')\n",
    )
    assert goal_met({"type": "print", "lines": ["Bea"]}, world)[0]
    assert goal_met({"type": "print", "text": "Bea"}, world)[0]
    assert goal_met({"type": "file", "name": "a.txt", "text": "xy"}, world)[0]
    assert goal_met({"type": "file", "name": "a.txt", "contains": "y"}, world)[0]
    assert not goal_met({"type": "file", "name": "b.txt", "text": ""}, world)[0]
    assert goal_met({"type": "time", "within": 1}, world)[0]
    assert goal_errors({"type": "time", "within": 0}, None)
    assert goal_errors({"type": "file", "name": "a.txt"}, None)


def test_world_inputs_and_data_are_checked():
    with pytest.raises(ValueError, match="inputs"):
        World.from_spec({"tiles": ["."], "start": [0, 0, "east"], "inputs": [1]})
    with pytest.raises(ValueError, match="data"):
        World.from_spec({"tiles": ["."], "start": [0, 0, "east"], "data": ["x"]})


def test_islands_lock_on_older_pythons():
    island = find_level("i312-l01")
    if versions.HOST < (3, 12):
        assert "this computer runs Python 3.11" in lock_reason(island)
    else:
        assert lock_reason(island) is None
        assert "choose Python 3.12" in lock_reason(island, (3, 11))
    run = run_level(island, 'say(f"{"a"}")\n', python=(3, 11))
    assert run.locked and not run.parsed.ok
    newest = find_level("i315-l01")
    if versions.HOST < (3, 15):
        assert "this computer runs" in lock_reason(newest)
        assert solution_errors(newest) == []  # skipped here, checked on 3.15 in CI


def test_debugging_starters_of_phase_four_need_fixing():
    for level in LEVELS:
        if level.id[:3] in ("m11", "m12", "m13", "m14", "m15") and level.starter:
            run = run_level(level, level.starter)
            assert run.check is None or not run.check.solved, level.id


def test_dispatch_answers_like_the_http_api(tmp_path):
    store = ProfileStore(tmp_path)
    info = dispatch("GET", "/api/info", {}, {}, store)
    assert info["default"] == versions.version_text(versions.DEFAULT)
    levels = dispatch("GET", "/api/levels", {"python": "3.11"}, {}, store)
    island = next(lvl for lvl in levels if lvl["id"] == "i312-l01")
    assert island["minPython"] == "3.12" and island["locked"]
    data = json.loads(dispatch_json("GET", "/api/levels/nope", "{}", "{}", store, "sk"))
    assert data["status"] == 404
    level = json.loads((level_files()[0]).read_text(encoding="utf-8"))
    preview = dispatch("POST", "/api/levels/preview", {}, {"level": level}, store)
    assert preview["id"] == level["id"] and preview["worlds"]
    bad = json.loads(
        dispatch_json("POST", "/api/levels/preview", "{}", '{"level": {}}', store, "en")
    )
    assert bad["status"] == 400


def test_run_json_has_lanes_time_and_files(tmp_path):
    store = ProfileStore(tmp_path)
    solution = (find_level("m14-l02").path.with_name("l02.solution.py")).read_text(encoding="utf-8")
    data = dispatch("POST", "/api/run", {}, {"level": "m14-l02", "source": solution}, store)
    assert data["check"]["solved"] and data["time"] == 4
    assert "arm 0" in data["lanes"]
    lanes = [step["lane"] for step in data["steps"]]
    first = next(i for i, lane in enumerate(lanes) if lane)
    assert all(lanes[first:]) and data["steps"][first]["time"] == 0


def test_graduate_writes_a_plain_python_file(tmp_path):
    program = tmp_path / "quiz.py"
    program.write_text("say('hi')\nstep(2)\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["graduate", str(program), "--run"])
    assert result.exit_code == 0, result.output
    real = (tmp_path / "quiz_real.py").read_text(encoding="utf-8")
    assert real.endswith("say('hi')\nstep(2)\n") and "def step" in real


def test_build_web_makes_an_offline_site(tmp_path):
    out = tmp_path / "site"
    result = CliRunner().invoke(main, ["build-web", str(out), "--pyodide", "pyodide"])
    assert result.exit_code == 0, result.output
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "CODEZOO_OFFLINE" in page and '"pyodide/"' in page
    worker = (out / "sw.js").read_text(encoding="utf-8")
    assert "__FILES__" not in worker and '"engine.zip"' in worker
    assert not (out / "sw.template.js").exists()
    with zipfile.ZipFile(out / "engine.zip") as archive:
        names = archive.namelist()
    assert "mse_codezoo/server.py" in names and "mse_codezoo/locale/sk.json" in names
    assert not any(name.startswith("mse_codezoo/web/") for name in names)
    assert (out / "cards-octopus-sk.html").is_file()


def test_levels_validate_reports_skipped_islands():
    result = CliRunner().invoke(main, ["levels", "validate", str(find_level("i315-l01").path)])
    if versions.HOST < (3, 15):
        assert "skip" in result.output and result.exit_code == 0
    else:
        assert result.exit_code == 0


def test_no_sticker_news_after_a_failed_run(tmp_path):
    store = ProfileStore(tmp_path)
    store.add("Ada", "bee")
    data = store.progress("Ada")
    data["levels"]["m01-l01"] = {"stars": 3, "solved": True}  # solved before stickers counted
    store._save_progress(store.find("Ada").id, data)
    body = {"level": "m01-l02", "source": "step(99)\n", "profile": "Ada"}
    failed = dispatch("POST", "/api/run", {}, body, store)
    assert not failed["check"]["solved"] and failed["newStickers"] == []
    body = {"level": "m01-l01", "source": "step(4)\ngrab()\n", "profile": "Ada"}
    solved = dispatch("POST", "/api/run", {}, body, store)
    assert [s["id"] for s in solved["newStickers"]] == ["first:solve"]


@pytest.mark.parametrize("lang", ["en", "sk"])
def test_core_level_titles_name_the_playing_animals_items(lang):
    from mse_codezoo.i18n import use_lang
    from mse_codezoo.levels import animal_names

    with use_lang(lang):
        monkey = load_pack("monkey")._names()["items"]
        words = {form.lower() for forms in monkey.values() for form in forms.values()}
        for level in LEVELS:
            if level.signature:
                continue
            for animal in animal_names():
                if animal == "monkey":
                    continue
                title = level.title_for(animal).lower()
                assert "{" not in title, (level.id, animal, title)
                assert not any(word in title for word in words), (level.id, animal, title)


def test_level_list_and_level_follow_the_chosen_animal(tmp_path):
    store = ProfileStore(tmp_path)
    listed = dispatch("GET", "/api/levels", {"animal": "bee"}, {}, store)
    assert next(lvl for lvl in listed if lvl["id"] == "m01-l01")["title"] == "One flower"
    level = dispatch("GET", "/api/levels/m01-l01", {"animal": "bee"}, {}, store)
    assert level["title"] == "One flower"
    own = dispatch("GET", "/api/levels/m01-l01", {}, {}, store)
    assert own["title"] == "One banana"


@pytest.mark.parametrize(
    ("spec", "source", "near", "distance"),
    [
        ({"tiles": ["...B"], "start": [0, 0, "east"]}, "step(2)\ngrab()\n", "ahead", 1),
        ({"tiles": ["B..."], "start": [3, 0, "east"]}, "grab()\n", "behind", 3),
        ({"tiles": ["..", ".B"], "start": [1, 0, "east"]}, "grab()\n", "right", 1),
        ({"tiles": ["..", ".B"], "start": [1, 0, "west"]}, "grab()\n", "left", 1),
        ({"tiles": [".t"], "items": [[1, 0, "B"]], "start": [0, 0, "east"]}, "grab()\n", "up", 1),
        ({"tiles": ["......B"], "start": [0, 0, "south"]}, "grab()\n", "none", None),
    ],
)
def test_a_missed_grab_says_where_the_item_is(spec, source, near, distance):
    world, result = run_in(spec, source)
    assert result.error is None
    (miss,) = world.misses
    assert miss["near"] == near and miss.get("distance") == distance
    events = [e for step in result.steps for e in step.events if e["type"] == "grab"]
    assert events[0]["item"] is None and events[0]["near"] == near


def test_a_missed_grab_explains_itself_and_counts_as_a_mistake():
    from mse_codezoo.game import attempt_from_run

    level = find_level("m01-l01")
    run = run_level(level, "step(3)\ngrab()\n", animal="beaver")
    assert "one step further on" in run.check.message
    assert attempt_from_run(run, "").mistakes == ["grab_miss"]
    walked_off = run_level(level, "step(9)\n")
    assert "further on" not in walked_off.check.message  # a bump says what it says
