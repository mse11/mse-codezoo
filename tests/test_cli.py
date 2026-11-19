import json

from click.testing import CliRunner

from mse_codezoo import __version__
from mse_codezoo.cli import main


def invoke(*args: str):
    return CliRunner().invoke(main, list(args))


def test_version():
    result = invoke("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_commands():
    result = invoke("--help")
    assert result.exit_code == 0
    for command in ("run", "check", "blocks", "levels"):
        assert command in result.output


def test_stub_commands_fail_cleanly(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("step(1)\n", encoding="utf-8")
    result = invoke("run", "m01-l01", str(program))
    assert result.exit_code == 1
    assert "not implemented yet" in result.output


def test_levels_list_runs():
    result = invoke("levels", "list")
    assert result.exit_code == 0
    assert "level(s)" in result.output


def test_levels_validate_all_passes_for_bundled_levels():
    result = invoke("levels", "validate", "--all")
    assert result.exit_code == 0, result.output


def test_levels_validate_needs_a_target():
    result = invoke("levels", "validate")
    assert result.exit_code == 2


def test_levels_validate_reports_problems(tmp_path):
    level = tmp_path / "l01.json"
    level.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    result = invoke("levels", "validate", str(tmp_path))
    assert result.exit_code == 1
    assert "missing keys" in result.output
    assert "missing reference solution" in result.output


def test_levels_validate_accepts_good_level(tmp_path):
    level = tmp_path / "l01.json"
    level.write_text(
        json.dumps(
            {"id": "m01-l01", "module": "sequences", "concepts": [], "world": {}, "goal": {}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "l01.solution.py").write_text("step(1)\n", encoding="utf-8")
    result = invoke("levels", "validate", str(level))
    assert result.exit_code == 0, result.output
    assert "1/1 level(s) valid" in result.output
