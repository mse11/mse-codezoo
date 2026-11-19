"""Profiles, progress, daily time and grown-up settings, stored as local JSON files."""

import datetime as dt
import json

import pytest

from mse_codezoo.game import attempt_from_run, run_level
from mse_codezoo.levels import find_level, level_files, load_level
from mse_codezoo.profiles import (
    Attempt,
    PinError,
    ProfileError,
    ProfileStore,
    classify_mistakes,
    default_home,
)


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "home")


def solve(store, player, level_id, source):
    run = run_level(find_level(level_id), source)
    return store.record(player, attempt_from_run(run, source))


def test_default_home_honours_codezoo_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path))
    assert default_home() == tmp_path


def test_default_home_is_a_codezoo_folder(monkeypatch):
    monkeypatch.delenv("CODEZOO_HOME", raising=False)
    assert default_home().name.lower() == "codezoo"


def test_add_find_and_list(store):
    ema = store.add("  Ema  ", "fox")
    assert ema.name == "Ema" and ema.picture == "fox"
    assert store.find("ema") == ema
    assert store.find(ema.id) == ema
    assert [p.name for p in store.profiles()] == ["Ema"]


@pytest.mark.parametrize(
    ("name", "picture", "message"),
    [
        ("", "fox", "type a name"),
        ("x" * 25, "fox", "at most 24"),
        ("Tom", "dragon", "Pick one of these pictures"),
    ],
)
def test_add_rejects_bad_input(store, name, picture, message):
    with pytest.raises(ProfileError, match=message):
        store.add(name, picture)


def test_names_are_unique_ignoring_case(store):
    store.add("Ema", "fox")
    with pytest.raises(ProfileError, match="already a player"):
        store.add("EMA", "owl")


def test_unknown_player(store):
    with pytest.raises(ProfileError, match="No player"):
        store.find("nobody")
    with pytest.raises(ProfileError):
        store.progress("p../../etc")


def test_progress_keeps_the_best_stars_and_counts_attempts(store):
    store.add("Ema", "fox")
    first = solve(store, "Ema", "m02-l01", "step(1)\ngrab()\n" * 5)
    assert first["stars"] == 1 and first["solved"] is True and first["attempts"] == 1
    best = solve(store, "Ema", "m02-l01", "for i in range(5):\n    step(1)\n    grab()\n")
    assert best["stars"] == 3 and best["attempts"] == 2
    again = solve(store, "Ema", "m02-l01", "step(1)\n")
    assert again["stars"] == 3 and again["solved"] is True and again["attempts"] == 3
    assert again["bestProgram"].startswith("for i in range(5):")
    mistakes = store.progress("Ema")["mistakes"]
    assert mistakes == {"too_long": 1, "missing_concept": 1, "not_finished": 1}


def test_parse_errors_are_recorded_as_syntax_mistakes(store):
    store.add("Ema", "fox")
    solve(store, "Ema", "m01-l01", "step(\n")
    assert store.progress("Ema")["mistakes"] == {"syntax": 1}


def test_private_mode_keeps_only_stars_and_solved(store):
    store.add("Ema", "fox")
    store.update_parent(private_mode=True)
    entry = solve(store, "Ema", "m01-l01", "step(4)\ngrab()\n")
    assert entry == {"stars": 3, "solved": True, "concepts": ["call"]}
    assert store.progress("Ema")["mistakes"] == {}


def test_time_and_daily_limit(store):
    store.add("Ema", "fox")
    assert store.today_status("Ema") == {"minutesToday": 0, "limitMinutes": None, "over": False}
    store.update_parent(daily_minutes=2)
    store.add_time("Ema", 60)
    status = store.add_time("Ema", 9999)  # capped per tick
    assert status["minutesToday"] == 3.0
    assert status["over"] is True
    store.add_time("Ema", -50)  # ignored
    assert store.today_status("Ema")["minutesToday"] == 3.0


def test_private_mode_keeps_only_today_for_the_limit(store):
    store.add("Ema", "fox")
    data = store.progress("Ema")
    data["time"] = {"2020-01-01": 600}
    store._save_progress(store.find("Ema").id, data)
    store.update_parent(private_mode=True)
    store.add_time("Ema", 30)
    assert list(store.progress("Ema")["time"]) == [dt.date.today().isoformat()]


def test_pin_protects_settings(store):
    store.update_parent(new_pin="2468", daily_minutes=30)
    assert store.parent().has_pin
    raw = json.loads((store.root / "parent.json").read_text(encoding="utf-8"))
    assert "2468" not in json.dumps(raw)  # only a salted hash is stored
    with pytest.raises(PinError, match="needs the grown-up PIN"):
        store.update_parent(daily_minutes=60)
    with pytest.raises(PinError, match="not right"):
        store.update_parent(pin="1111", daily_minutes=60)
    store.update_parent(pin="2468", daily_minutes=None)
    assert store.parent().daily_minutes is None
    store.update_parent(pin="2468", clear_pin=True)
    assert not store.parent().has_pin


@pytest.mark.parametrize("bad", [0, 601, True, "30"])
def test_daily_limit_range(store, bad):
    with pytest.raises(ProfileError, match="between 1 and 600"):
        store.update_parent(daily_minutes=bad)


@pytest.mark.parametrize("bad", ["12", "abcd", "123456789"])
def test_pin_format(store, bad):
    with pytest.raises(ProfileError, match="4 to 8 digits"):
        store.update_parent(new_pin=bad)


def test_parent_settings_are_not_in_the_export(store):
    store.add("Ema", "fox")
    store.update_parent(new_pin="2468")
    solve(store, "Ema", "m01-l01", "step(4)\ngrab()\n")
    exported = json.dumps(store.export("Ema"))
    assert "pin" not in exported and "daily" not in exported


def test_export_import_round_trip(store, tmp_path):
    store.add("Ema", "fox")
    solve(store, "Ema", "m01-l01", "step(4)\ngrab()\n")
    data = store.export("Ema")
    other = ProfileStore(tmp_path / "other")
    imported = other.import_(data)
    assert imported.name == "Ema" and imported.id != store.find("Ema").id
    assert other.progress("Ema")["levels"]["m01-l01"]["stars"] == 3
    again = other.import_(data)  # same name already there
    assert again.name == "Ema (2)"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"format": "zip"},
        {"format": "codezoo-profile", "profile": {"name": "X"}, "progress": {"levels": []}},
    ],
)
def test_import_rejects_bad_files(store, data):
    with pytest.raises(ProfileError):
        store.import_(data)
    assert store.profiles() == []


def test_remove_deletes_progress(store):
    ema = store.add("Ema", "fox")
    solve(store, "Ema", "m01-l01", "step(4)\ngrab()\n")
    path = store.root / "progress" / f"{ema.id}.json"
    assert path.exists()
    store.remove("Ema")
    assert not path.exists()
    assert store.profiles() == []


def test_report(store):
    store.add("Ema", "fox")
    solve(store, "Ema", "m02-l01", "for i in range(5):\n    step(1)\n    grab()\n")
    solve(store, "Ema", "m02-l02", "for i in range(9):\n    step(1)\n    grab()\n")
    solve(store, "Ema", "m01-l03", "step(2)\n")  # bump
    report = store.report("Ema", [load_level(p) for p in level_files()])
    status = {row["concept"]: row["status"] for row in report["concepts"]}
    assert status["for"] == "mastered"
    assert status["order"] == "met"
    assert status["comment"] == "not yet"
    assert report["levelsSolved"] == 2 and report["stars"] == 6
    assert report["mistakes"][0]["kind"] == "bump"


@pytest.mark.parametrize(
    ("solved", "stars", "error", "kinds"),
    [
        (False, [], "bump", ["bump"]),
        (False, [], "unknown_name", ["unknown_name"]),
        (False, [], "syntax", ["syntax"]),
        (False, [], "too_many_steps", ["endless_loop"]),
        (False, [], "type", ["type_mixup"]),
        (False, [], "other", []),
        (False, [(False, "")] * 3, None, ["not_finished"]),
        (True, [(True, ""), (False, ""), (False, "")], None, ["too_long", "missing_concept"]),
        (True, [(True, "")] * 3, None, []),
    ],
)
def test_classify_mistakes(solved, stars, error, kinds):
    assert classify_mistakes(solved, stars, error) == kinds


def test_no_temporary_files_are_left_behind(store):
    store.add("Ema", "fox")
    store.record("Ema", Attempt("m01-l01", ["call"], True, 3))
    assert not list(store.root.rglob("*.tmp"))


def test_damaged_file_gives_a_friendly_error(store):
    store.root.mkdir(parents=True)
    (store.root / "profiles.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(ProfileError, match="Can't read profiles.json"):
        store.profiles()
