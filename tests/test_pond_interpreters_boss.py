"""The pond (the console's >>> prompt), concurrent.interpreters (3.14) and the
free-threading boss level."""

import json
import threading
import urllib.request

import pytest

from mse_codezoo import interpreter
from mse_codezoo.game import run_level
from mse_codezoo.lang_python import parse
from mse_codezoo.levels import find_level
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.repl import Ponds
from mse_codezoo.server import CodeZooServer


def feed_all(lines, version=(3, 13)):
    ponds, session, replies = Ponds(), None, []
    for line in lines:
        reply = ponds.feed(session, line, version)
        session = reply["session"]
        replies.append(reply)
    return replies


# --- the pond --------------------------------------------------------------------------


def test_the_pond_keeps_variables_and_shows_values():
    replies = feed_all(["fish = 3", "fish * 2", "_ + 1", "names = ['a']", "names"])
    assert [r["output"] for r in replies] == [[], ["6"], ["7"], [], ["['a']"]]
    assert not any(r["error"] for r in replies)


def test_a_block_goes_on_until_a_blank_line():
    replies = feed_all(["for i in range(2):", "    print('hop', i)", ""])
    assert [r["more"] for r in replies] == [True, True, False]
    assert replies[-1]["output"] == ["hop 0", "hop 1"]


def test_mistakes_get_the_zoos_kind_messages_and_the_pond_goes_on():
    replies = feed_all(["print(missing)", "1 +", "2 + 2", "x = " + "1" * 500])
    assert "missing" in replies[0]["error"] and replies[1]["error"]
    assert replies[2]["output"] == ["4"]
    assert replies[3]["error"]  # one line at most 400 characters


def test_a_runaway_line_stops_at_the_step_limit():
    replies = feed_all(["while True:", "    pass", ""])
    assert replies[-1]["error"]


def test_the_pond_over_the_api(tmp_path):
    server = CodeZooServer("127.0.0.1", 0, store=ProfileStore(tmp_path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(body):
        request = urllib.request.Request(base + "/api/pond", data=json.dumps(body).encode())
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    try:
        first = post({"line": "fish = 5"})
        second = post({"session": first["session"], "line": "fish + 1"})
        assert second["output"] == ["6"] and second["session"] == first["session"]
    finally:
        server.shutdown()
        server.server_close()


# --- concurrent.interpreters (Python 3.14) ----------------------------------------------

INTERPRETERS = """from concurrent import interpreters

fish = 3
interp = interpreters.create()
interp.exec("fish = 10\\nprint('inside', fish)")
interp.exec("print('still', fish + 1)")
print("outside", fish)
print(len(interpreters.list_all()))
interp.close()
print(len(interpreters.list_all()))
"""


def test_interpreters_share_nothing():
    result = interpreter.run(parse(INTERPRETERS, (3, 14)).program, version=(3, 14))
    assert result.error is None, result.error.message
    assert result.output == ["inside 10", "still 11", "outside 3", "1", "0"]


def test_interpreters_arrived_in_3_14():
    result = interpreter.run(parse(INTERPRETERS, (3, 13)).program, version=(3, 13))
    assert "arrived in Python 3.14" in result.error.message


def test_an_interpreter_reports_its_own_mistakes():
    source = (
        "from concurrent import interpreters\ninterp = interpreters.create()\n"
        "interp.exec('print(missing)')\n"
    )
    result = interpreter.run(parse(source, (3, 14)).program, version=(3, 14))
    assert "The interpreter stopped" in result.error.message


# --- the free-threading boss level -------------------------------------------------------


def test_the_boss_level_loses_fish_until_there_is_a_lock():
    level = find_level("i313-l03")
    assert len(level.worlds()) == 2  # with the GIL, and free-threaded
    for variant in (0, 1):
        broken = run_level(level, level.starter, variant=variant)
        assert not broken.check.solved
        assert broken.result.output[-1] != "fish: 200"
    counted = int(broken.result.output[-1].split()[-1])
    assert counted < 200  # free-threaded: fish get lost
    fixed_source = level.starter.replace("fish = 0\n", "fish = 0\nlock = threading.Lock()\n")
    fixed_source = fixed_source.replace(
        "        seen = fish\n        fish = seen + 1\n",
        "        with lock:\n            seen = fish\n            fish = seen + 1\n",
    )
    for variant in (0, 1):
        assert run_level(level, fixed_source, variant=variant).check.solved


@pytest.mark.parametrize("key", ["lambda", "with", "match"])
def test_the_new_blocks_are_in_the_palette(key):
    from pathlib import Path

    blocks = (Path(__file__).parent.parent / "mse_codezoo" / "web" / "blocks.js").read_text(
        encoding="utf-8"
    )
    assert f"  {key}: {{ type:" in blocks or f"  {key}: {{\n" in blocks
    assert "cz_case_raw" in blocks  # any other pattern is kept exactly
