import json

import pytest
from click.testing import CliRunner

from mse_codezoo import __version__
from mse_codezoo.cli import main

GOOD = {
    "id": "t-l01",
    "module": "test",
    "concepts": [],
    "world": {"tiles": [".B"], "start": [0, 0, "east"]},
    "goal": {"type": "collect_all", "item": "B"},
}


def invoke(*args):
    return CliRunner().invoke(main, [str(a) for a in args])


@pytest.fixture
def program(tmp_path):
    def write(source):
        path = tmp_path / "program.py"
        path.write_text(source, encoding="utf-8")
        return path

    return write


def test_version():
    result = invoke("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_commands():
    result = invoke("--help")
    assert result.exit_code == 0
    for command in ("run", "check", "blocks", "levels"):
        assert command in result.output


def test_run_prints_grid_and_finishes(program):
    result = invoke("run", "m01-l01", program("step(4)\ngrab()\nprint('done')\n"))
    assert result.exit_code == 0, result.output
    assert "Level m01-l01: One banana (monkey)" in result.output
    assert "printed: done" in result.output
    assert "Finished in 3 steps." in result.output


def test_run_trace_shows_lines_events_and_grid(program):
    result = invoke("run", "m01-l01", program("step(1)\n"), "--trace")
    assert result.exit_code == 0, result.output
    assert "   1 | step(1)" in result.output
    assert "moved to (1, 0)" in result.output
    assert ".>..B" in result.output


def test_run_error_exits_1_with_the_line(program):
    result = invoke("run", "m01-l01", program("step(1)\nstep(9)\n"))
    assert result.exit_code == 1
    assert "line 2: Bump! The monkey reached the edge of the jungle." in result.output


def test_run_syntax_error(program):
    result = invoke("run", "m01-l01", program("step(\n"))
    assert result.exit_code == 1
    assert "line 1: error: Python can't read line 1" in result.output


def test_run_json(program):
    result = invoke("run", "m01-l01", program("step(4)\ngrab()\n"), "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["check"]["solved"] is True
    assert data["program"]["type"] == "Program"
    assert [step["line"] for step in data["steps"]] == [1, 2]
    assert data["world"]["collected"] == {"B": 1}


def test_unknown_level(program):
    result = invoke("run", "m99-l99", program("step(1)\n"))
    assert result.exit_code == 1
    assert "No level called 'm99-l99'" in result.output


def test_check_solved_shows_stars(program):
    result = invoke("check", "m02-l01", program("for i in range(5):\n    step(1)\n    grab()\n"))
    assert result.exit_code == 0, result.output
    assert "Stars: 3/3" in result.output
    assert "[x] Used a `for` loop" in result.output


def test_check_unsolved_shows_hint_and_exits_1(program):
    result = invoke("check", "m01-l01", program("step(1)\n"))
    assert result.exit_code == 1
    assert "1 banana still to collect." in result.output
    assert "Stars: 0/3" in result.output
    assert "Hint: Count the squares" in result.output


def test_blocks_outline(program):
    result = invoke("blocks", program("# go\nfor i in range(2):\n    step(1)\n"))
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].endswith("note: go")
    assert "repeat 2 times (i counts)" in lines[1]
    assert lines[2].endswith("        step 1")


def test_levels_list():
    result = invoke("levels", "list")
    assert result.exit_code == 0
    assert "m01-l01    One banana" in result.output


def test_levels_show():
    result = invoke("levels", "show", "m01-l03")
    assert result.exit_code == 0, result.output
    assert "Level m01-l03: Around the rock (monkey)" in result.output
    assert "Goal: collect every banana" in result.output
    assert "Stars for: 7 lines or fewer" in result.output
    assert "    >#B\n    ...\n" in result.output
    assert "Hint 1:" in result.output
    assert "Reference solution" not in result.output


def test_levels_show_solution():
    result = invoke("levels", "show", "m02-l01", "--solution")
    assert result.exit_code == 0, result.output
    assert "Stars for: 3 lines or fewer; use For" in result.output
    assert "Reference solution:\n    for i in range(5):" in result.output


def test_levels_show_unknown_level():
    result = invoke("levels", "show", "nope")
    assert result.exit_code == 1
    assert "No level called 'nope'" in result.output


def test_levels_validate_all_passes_for_bundled_levels():
    result = invoke("levels", "validate", "--all")
    assert result.exit_code == 0, result.output
    assert "ok    m01-sequences/l01.json" in result.output


def test_levels_validate_needs_a_target():
    assert invoke("levels", "validate").exit_code == 2


def test_levels_validate_reports_problems(tmp_path):
    (tmp_path / "l01.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    result = invoke("levels", "validate", tmp_path)
    assert result.exit_code == 1
    assert "missing keys" in result.output
    assert "missing reference solution" in result.output


def test_levels_validate_runs_the_solution(tmp_path):
    (tmp_path / "l01.json").write_text(json.dumps(GOOD), encoding="utf-8")
    (tmp_path / "l01.solution.py").write_text("step(1)\n", encoding="utf-8")
    result = invoke("levels", "validate", tmp_path / "l01.json")
    assert result.exit_code == 1
    assert "earns 0/3 stars" in result.output

    (tmp_path / "l01.solution.py").write_text("step(1)\ngrab()\n", encoding="utf-8")
    result = invoke("levels", "validate", tmp_path / "l01.json")
    assert result.exit_code == 0, result.output
    assert "1/1 level(s) valid" in result.output
