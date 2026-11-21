"""Phase 6: pilot readiness. Opt-in pilot recording, concept checks, the anonymised export,
the pilot report, API levels by id only, the bundled Pyodide and the teacher's controls."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from mse_codezoo import pilot
from mse_codezoo.classes import ClassStore
from mse_codezoo.cli import main
from mse_codezoo.hub import Hub
from mse_codezoo.i18n import use_lang
from mse_codezoo.levels import find_level, level_files, load_level
from mse_codezoo.profiles import PinError, ProfileError, ProfileStore
from mse_codezoo.server import ApiError, dispatch
from mse_codezoo.webbuild import PYODIDE_FILES, build

LEVELS = [load_level(p) for p in level_files()]
SOLUTION = "step(4)\ngrab()\n"  # m01-l01


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path)


def turned_on(store):
    store.update_parent(pilot=True)
    return store.add("Ema", "fox")


def run(store, profile, level="m01-l01", source=SOLUTION, hints=0):
    body = {"level": level, "source": source, "profile": profile.id, "hints": hints}
    return dispatch("POST", "/api/run", {}, body, store)


# --- recording is opt-in ------------------------------------------------------------------


def test_nothing_is_recorded_until_a_grown_up_turns_the_pilot_on(store):
    ema = store.add("Ema", "fox")
    answer = dispatch(
        "POST", f"/api/profiles/{ema.id}/pilot", {}, {"event": "open", "level": "m01-l01"}, store
    )
    assert answer == {"pilot": False}
    run(store, ema)
    assert "pilot" not in store.progress(ema.id)
    assert dispatch("GET", f"/api/profiles/{ema.id}/progress", {}, {}, store)["pilot"] is False


def test_private_mode_wins_over_the_pilot(store):
    ema = turned_on(store)
    store.update_parent(private_mode=True)
    assert not pilot.enabled(store)
    run(store, ema)
    assert "pilot" not in store.progress(ema.id)


def test_opening_and_solving_levels_record_the_pilot_metrics(store):
    ema = turned_on(store)
    opened = dispatch(
        "POST", f"/api/profiles/{ema.id}/pilot", {}, {"event": "open", "level": "m01-l01"}, store
    )
    assert opened == {"pilot": True, "check": {"module": "sequences", "phase": "before"}}
    run(store, ema, hints=1)
    data = store.progress(ema.id)["pilot"]
    assert data["id"].startswith("P-") and len(data["id"]) == 8
    assert data["start"] <= data["firstStar"]
    hints_total = len(find_level("m01-l01").hints)
    assert data["hintsAtSolve"]["m01-l01"] == [1, hints_total]
    run(store, ema, hints=5)  # only the first solve counts
    assert store.progress(ema.id)["pilot"]["hintsAtSolve"]["m01-l01"] == [1, hints_total]


def test_events_from_the_page(store):
    ema = turned_on(store)
    path = f"/api/profiles/{ema.id}/pilot"
    dispatch("POST", path, {}, {"event": "error"}, store)
    dispatch("POST", path, {}, {"event": "smiley", "value": 4}, store)
    data = store.progress(ema.id)["pilot"]
    assert data["errors"] == 1 and list(data["smileys"].values()) == [4]
    assert dispatch("GET", f"/api/profiles/{ema.id}/progress", {}, {}, store)["smileyDue"] is False
    for bad in (
        {"event": "smiley", "value": 9},
        {"event": "smiley", "value": True},
        {"event": "x"},
    ):
        with pytest.raises(ProfileError):
            dispatch("POST", path, {}, bad, store)


# --- concept checks -------------------------------------------------------------------------


def test_every_question_is_complete():
    checks = pilot.load_checks()
    assert set(checks) >= {"sequences", "loops-1", "variables", "text", "conditions"}
    concepts = {c for level in LEVELS for c in level.concepts}
    for module, items in checks.items():
        assert module in {level.module for level in LEVELS}
        assert len(items) >= 3
        for q in items:
            assert {"en", "sk"} <= set(q["prompt"]), q["id"]
            assert 0 <= q["answer"] < len(q["choices"]), q["id"]
            assert q["concept"] in concepts, q["id"]
            for choice in q["choices"]:
                assert "code" in choice or {"en", "sk"} <= set(choice), q["id"]


def test_questions_are_sent_without_answers_and_in_the_language(store):
    with use_lang("sk"):
        data = dispatch("GET", "/api/checks/sequences", {}, {}, store)
    assert data["questions"][0]["prompt"].startswith("Opička")
    assert all("answer" not in q for q in data["questions"])
    assert dispatch("GET", "/api/checks/no-such-module", {}, {}, store)["questions"] == []


def test_checks_before_and_after_a_module(store):
    ema = turned_on(store)
    path = f"/api/profiles/{ema.id}/check"
    body = {"module": "sequences", "phase": "before", "answers": [0, 1, 0]}
    assert dispatch("POST", path, {}, body, store) == {"ok": True}
    before = store.progress(ema.id)["pilot"]["checks"]["sequences"]["before"]
    assert before["right"] == 1 and before["of"] == 3 and not before["skipped"]
    with pytest.raises(ProfileError):
        dispatch("POST", path, {}, {**body, "answers": [0]}, store)
    # solving most of the module makes the "after" check due, once
    module = [lv for lv in LEVELS if lv.module == "sequences"]
    solutions = {lv.id: (lv.path.parent / f"{lv.path.stem}.solution.py") for lv in module}
    results = [
        run(store, ema, lv.id, solutions[lv.id].read_text(encoding="utf-8")) for lv in module
    ]
    due = [r["pilotCheck"] for r in results if "pilotCheck" in r]
    assert all("solved" in r["check"] for r in results)  # the goal check is untouched
    assert due and due[0] == {"module": "sequences", "phase": "after"}
    skip = {"module": "sequences", "phase": "after", "answers": [None, None, None]}
    dispatch("POST", path, {}, skip, store)
    assert store.progress(ema.id)["pilot"]["checks"]["sequences"]["after"]["skipped"]
    assert pilot.due_check(store.progress(ema.id), "sequences", LEVELS) is None


# --- export and report ----------------------------------------------------------------------


def test_the_export_holds_no_names_pictures_or_programs(store):
    ema = turned_on(store)
    store.add("Noah", "owl")  # never played in the pilot: not in the file
    run(store, ema, source="step(4)\ngrab()  # Ema's secret note\n")
    store.update_parent(new_pin="4321")
    with pytest.raises(PinError):
        dispatch("POST", "/api/parent/pilot-export", {}, {}, store)
    answer = dispatch("POST", "/api/parent/pilot-export", {}, {"pin": "4321"}, store)
    text = json.dumps(answer["file"])
    for private in ("Ema", "Noah", "fox", "owl", "secret", "step(4)", ema.id):
        assert private not in text
    assert [p["pilotId"] for p in answer["file"]["players"]] == [
        store.progress(ema.id)["pilot"]["id"]
    ]
    assert any("no names" in line for line in answer["contents"])


def test_age_bands(store):
    ema = turned_on(store)
    body = {"profile": ema.id, "ageBand": "8-9"}
    assert dispatch("POST", "/api/parent/age", {}, body, store)["ageBand"] == "8-9"
    with pytest.raises(ProfileError):
        dispatch("POST", "/api/parent/age", {}, {**body, "ageBand": "9"}, store)
    report = dispatch("POST", "/api/parent/report", {}, {"profile": ema.id}, store)
    assert report["pilot"]["ageBand"] == "8-9"


def player(pid, *, minutes, solved_after_hints, gain, smiley, opened=("a", "b")):
    return {
        "pilotId": pid,
        "ageBand": "8-9",
        "minutesToFirstStar": minutes,
        "levels": {"a": {"attempts": 1, "solved": True, "stars": 3}},
        "opened": list(opened),
        "hintsAtSolve": {"a": [solved_after_hints, 2]},
        "modules": {"m": {"started": True, "levels": 2, "solved": 1 + int(gain)}},
        "checks": {
            "m": {
                "before": {"skipped": False, "right": 1, "of": 3},
                "after": {"skipped": False, "right": 1 + int(gain), "of": 3},
            }
        },
        "errors": 0,
        "smileys": [smiley],
        "mistakes": {},
    }


def test_the_report_compares_every_metric_with_its_target():
    file = {
        "format": "codezoo-pilot",
        "players": [
            player("P-1", minutes=3, solved_after_hints=0, gain=True, smiley=5),
            player("P-2", minutes=9, solved_after_hints=2, gain=False, smiley=3),
            player("P-3", minutes=4, solved_after_hints=1, gain=True, smiley=4),
        ],
    }
    result = pilot.report([file])
    metrics = {m["metric"]: m for m in result["metrics"]}
    assert result["players"] == 3
    assert (
        metrics["medianMinutesToFirstStar"]["value"] == 4
        and metrics["medianMinutesToFirstStar"]["met"]
    )
    assert metrics["solvedBeforeLastHint"]["value"] == pytest.approx(2 / 3)
    assert metrics["learningGainShare"]["value"] == pytest.approx(2 / 3)
    assert (
        metrics["playAgainShare"]["value"] == pytest.approx(2 / 3)
        and not metrics["playAgainShare"]["met"]
    )
    assert metrics["moduleCompletion"]["value"] == pytest.approx(2 / 3)
    assert result["worstLevel"] == "b" and metrics["worstDropOff"]["value"] == 1
    with pytest.raises(ValueError):
        pilot.report([{"format": "something else"}])


def test_pilot_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path))
    store = ProfileStore(tmp_path)
    ema = turned_on(store)
    run(store, ema)
    runner = CliRunner()
    assert runner.invoke(main, ["parent", "set", "--no-pilot"]).exit_code == 0
    assert not store.parent().pilot
    assert runner.invoke(main, ["parent", "set", "--pilot"]).exit_code == 0
    out = tmp_path / "pilot.json"
    result = runner.invoke(main, ["pilot", "export", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "no names" in result.output
    result = runner.invoke(main, ["pilot", "report", str(out)])
    assert result.exit_code == 0, result.output
    assert "| Median minutes to the first star |" in result.output


# --- the classroom hub ----------------------------------------------------------------------


def test_the_teacher_turns_the_pilot_on_and_exports_it(tmp_path):
    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("3.B", "class").id)
    head = {"X-Teacher-Token": hub.teacher_token}
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"pilot": True}, head, "t")
    assert overview["pilot"] and overview["ageBands"]
    kid = hub.handle(
        "POST", "/api/teacher/player", {}, {"name": "Ema", "picture": "cat"}, head, "t"
    )
    hub.handle(
        "POST", "/api/teacher/player/age", {}, {"profile": kid["id"], "ageBand": "10-12"}, head, "t"
    )
    code = {"X-Class-Code": hub.code}
    body = {"level": "m01-l01", "source": SOLUTION, "profile": kid["id"], "hints": 0}
    hub.handle("POST", "/api/run", {}, body, code, "c")
    answer = hub.handle("POST", "/api/teacher/pilot-export", {}, {}, head, "t")
    assert answer["file"]["players"][0]["ageBand"] == "10-12"
    assert "Ema" not in json.dumps(answer["file"])


# --- hardening and the build ----------------------------------------------------------------


def test_api_requests_name_levels_by_id_only(store, tmp_path):
    level = json.loads(next(iter(level_files())).read_text(encoding="utf-8"))
    path = tmp_path / "elsewhere.json"
    path.write_text(json.dumps(level), encoding="utf-8")
    body = {"level": str(path), "source": SOLUTION}
    with pytest.raises(ApiError):
        dispatch("POST", "/api/run", {}, body, store)
    with pytest.raises(ApiError):
        dispatch("GET", f"/api/levels/{path}", {}, {}, store)


def test_the_site_can_carry_its_own_pyodide(tmp_path):
    fake = tmp_path / "pyodide"
    fake.mkdir()
    for name in PYODIDE_FILES:
        (fake / name).write_text("x", encoding="utf-8")
    site = tmp_path / "site"
    build(site, pyodide_dir=fake)
    assert all((site / "pyodide" / name).is_file() for name in PYODIDE_FILES)
    assert '"pyodide": "./pyodide/"' in (site / "index.html").read_text(encoding="utf-8")
    assert "CODEZOO_OFFLINE" in (site / "check.html").read_text(encoding="utf-8")
    assert not (site / "teacher.html").exists() and (site / "teacher.css").exists()
    assert "pyodide/pyodide.asm.wasm" in (site / "sw.js").read_text(encoding="utf-8")
    (fake / "pyodide.asm.wasm").unlink()
    with pytest.raises(FileNotFoundError):
        build(tmp_path / "site2", pyodide_dir=fake)


def test_pages_have_the_look_and_feel_button():
    web = Path(__file__).parents[1] / "mse_codezoo" / "web"
    for page in ("index.html", "teacher.html"):
        assert 'id="look"' in (web / page).read_text(encoding="utf-8")
    for script in ("app.js", "editor.js", "teacher.js", "check.js"):
        assert "./look.js" in (web / script).read_text(encoding="utf-8")
