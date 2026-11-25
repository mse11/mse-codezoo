"""The debugger: each step can carry the variables' values (interpreter.Runner._watch),
the web server sends them, and the page shows them in the Variables bar and beside the
code (web/debug.js)."""

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from mse_codezoo import interpreter
from mse_codezoo.lang_python import parse
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import CodeZooServer

WEB = Path(__file__).resolve().parent.parent / "mse_codezoo" / "web"


def scopes(source):
    result = interpreter.run(parse(source).program, watch=True)
    assert result.error is None, result.error
    return [step.scope for step in result.steps]


def replay(steps):
    """What the page does in debug.js: add the changes up, step by step."""
    globals_, locals_, calls, seen = {}, {}, [], []
    for scope in steps:
        scope = scope or {}
        for name in scope.get("g-", []):
            del globals_[name]
        globals_.update(scope.get("g", {}))
        if "f" in scope:
            calls, locals_ = scope["f"], {}
        for name in scope.get("l-", []):
            del locals_[name]
        locals_.update(scope.get("l", {}))
        seen.append((dict(globals_), list(calls), dict(locals_)))
    return seen


def test_watch_is_off_by_default():
    result = interpreter.run(parse("x = 1\n").program)
    assert result.steps[0].scope is None


def test_only_changes_are_sent():
    steps = scopes("x = 1\ny = 2\nx = 1\nx = 3\n")
    assert steps == [{"g": {"x": "1"}}, {"g": {"y": "2"}}, None, {"g": {"x": "3"}}]


def test_deleted_names_and_loops():
    steps = scopes("total = 0\nfor i in range(3):\n    total += i\ndel i\n")
    final = replay(steps)[-1]
    assert final[0] == {"total": "3"}
    assert steps[-1] == {"g-": ["i"]}


def test_calls_show_their_own_variables():
    source = "fish = 1\ndef add(n):\n    total = fish + n\n    return total\nx = add(5)\n"
    seen = replay(scopes(source))
    inside = [s for s in seen if s[1] == ["add"]]
    assert inside[0][2] == {"n": "5"}
    assert inside[-1][2] == {"n": "5", "total": "6"}
    globals_, calls, locals_ = seen[-1]
    assert globals_ == {"fish": "1", "x": "6"} and calls == [] and locals_ == {}


def test_recursion_keeps_the_newest_call():
    source = "def down(n):\n    if n > 0:\n        down(n - 1)\ndown(2)\n"
    seen = replay(scopes(source))
    assert max(len(s[1]) for s in seen) == 3
    assert any(s[1] == ["down", "down", "down"] and s[2] == {"n": "0"} for s in seen)


def test_functions_classes_and_modules_are_left_out_objects_show_attributes():
    source = (
        "import math\n"
        "class Dog:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "_hidden = 1\n"
        "d = Dog('Rex')\n"
        "f = len\n"
    )
    final = replay(scopes(source))[-1][0]
    assert final == {"d": "Dog(name='Rex')"}


def test_long_values_are_cut():
    final = replay(scopes("text = 'a' * 500\nbig = list(range(100))\n"))[-1][0]
    assert all(len(value) <= interpreter.MAX_WATCH_TEXT for value in final.values())
    assert final["text"].endswith("...") and final["big"].endswith(", ...]")


def test_an_error_step_still_has_the_values():
    result = interpreter.run(parse("x = 1\ny = x / 0\n").program, watch=True)
    assert result.error is not None
    assert replay([s.scope for s in result.steps])[-1][0] == {"x": "1"}


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    store = ProfileStore(tmp_path_factory.mktemp("codezoo-home"))
    server = CodeZooServer("127.0.0.1", 0, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_web_server_sends_the_values(base_url):
    body = json.dumps({"level": "m01-l01", "source": "n = 4\nstep(n)\ngrab()\n"}).encode()
    req = urllib.request.Request(base_url + "/api/run", data=body)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read())
    assert data["steps"][0]["scope"] == {"g": {"n": "4"}}
    assert data["steps"][1]["scope"] is None


def test_page_has_both_views():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="debug"' in page and page.count('class="pane-bug') == 3 and 'id="watch"' in page
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'from "./debug.js"' in app
    code = (WEB / "code.js").read_text(encoding="utf-8")
    assert "setValues" in code and "step-arrow" in code and "trail" not in code
    blocks = (WEB / "blocks.js").read_text(encoding="utf-8")
    assert "stepMarks" in blocks and "highlightBlock" not in blocks


# --- the first debugger level (module 1) ---------------------------------------------


def test_module_one_has_a_level_about_the_debugger():
    from mse_codezoo.game import level_to_json, run_level
    from mse_codezoo.levels import find_level

    level = find_level("m01-l07b")
    assert level.debug is True and "debugging" in level.concepts
    data = level_to_json(level)
    assert data["debug"] is True
    # the program counts its steps in `a`, but stops one square short: the debugger shows it
    run = run_level(level, level.starter, watch=True)
    assert not run.check.solved
    seen = replay([step.scope for step in run.result.steps])
    assert seen[-1][0] == {"a": "4"}
    assert "a" in level.starter and "say(f" in level.starter


def test_debug_must_be_true_or_false(tmp_path):
    import json as json_module

    from mse_codezoo.levels import validate_level

    data = {
        "id": "x-l01",
        "module": "sequences",
        "concepts": ["call"],
        "world": {"tiles": ["..B"], "start": [0, 0, "east"]},
        "goal": {"type": "collect_all", "item": "B"},
        "debug": "yes",
    }
    path = tmp_path / "l01.json"
    path.write_text(json_module.dumps(data), encoding="utf-8")
    (tmp_path / "l01.solution.py").write_text("step(2)\ngrab()\n", encoding="utf-8")
    assert "debug must be true or false" in validate_level(path).errors
