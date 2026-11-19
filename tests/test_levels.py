import json

import pytest

from mse_codezoo.game import run_level, solution_errors
from mse_codezoo.levels import (
    LevelError,
    find_level,
    level_files,
    load_level,
    load_pack,
    validate_level,
)

BUNDLED = level_files()


def test_at_least_five_levels_ship():
    assert len(BUNDLED) >= 5


@pytest.mark.parametrize("path", BUNDLED, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_bundled_level_is_valid_and_its_solution_earns_every_star(path):
    assert validate_level(path).errors == []
    assert solution_errors(load_level(path)) == []


def test_level_ids_are_unique():
    ids = [load_level(path).id for path in BUNDLED]
    assert len(ids) == len(set(ids))


def test_find_level_by_id_and_by_path():
    by_id = find_level("m01-l01")
    assert by_id.title == "One banana"
    assert find_level(str(by_id.path)).id == "m01-l01"
    with pytest.raises(LevelError, match="No level called"):
        find_level("m99-l99")


def test_load_pack():
    assert load_pack("monkey").item_name("B") == "banana"
    with pytest.raises(LevelError, match="No animal pack"):
        load_pack("dragon")


def test_run_level_reports_parse_errors_without_running():
    run = run_level(find_level("m01-l01"), "step(\n")
    assert not run.parsed.ok
    assert run.result is None and run.check is None


def test_run_level_line_of_error():
    run = run_level(find_level("m01-l01"), "step(1)\n\nstep(9)\n")
    assert run.line_of(run.result.error.node_id) == 3


def write_level(tmp_path, data, solution="step(1)\ngrab()\n"):
    path = tmp_path / "l01.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    if solution is not None:
        (tmp_path / "l01.solution.py").write_text(solution, encoding="utf-8")
    return path


GOOD = {
    "id": "t-l01",
    "module": "test",
    "concepts": [],
    "world": {"tiles": [".B"], "start": [0, 0, "east"]},
    "goal": {"type": "collect_all", "item": "B"},
}


def test_validate_reports_structural_problems(tmp_path):
    bad = {
        **GOOD,
        "world": {"tiles": [".B"], "start": [0, 0, "up"]},
        "goal": {"type": "dance"},
        "constraints": {"maxLines": 0, "mustUse": ["Teleport"]},
        "animal": "dragon",
    }
    errors = " | ".join(validate_level(write_level(tmp_path, bad, solution=None)).errors)
    for expected in (
        "missing reference solution",
        "world.start",
        "goal.type",
        "maxLines",
        "Teleport",
        "unknown animal",
    ):
        assert expected in errors


def test_validate_goal_item_must_exist(tmp_path):
    data = {**GOOD, "goal": {"type": "collect_all", "item": "Z"}}
    assert "does not appear" in validate_level(write_level(tmp_path, data)).errors[0]


def test_solution_that_misses_a_star_is_reported(tmp_path):
    data = {**GOOD, "constraints": {"maxLines": 1}}
    errors = solution_errors(load_level(write_level(tmp_path, data)))
    assert "earns 2/3 stars" in errors[0]
