import pytest

from mse_codezoo.interpreter import LearnerError, run
from mse_codezoo.lang_python import parse


def run_source(source, **kwargs):
    result = parse(source)
    assert result.ok, result.diagnostics
    return result, run(result.program, **kwargs)


def test_variables_loops_and_print():
    _, result = run_source("total = 0\nfor i in range(4):\n    total += i\nprint('total', total)\n")
    assert result.ok
    assert result.output == ["total 6"]


def test_every_statement_yields_a_step_with_its_node_id():
    parsed, result = run_source("x = 1\nfor i in range(2):\n    x += 1\n")
    program = parsed.program
    loop, body = program.body[1], program.body[1].body[0]
    ids = [step.node_id for step in result.steps]
    assert ids == [program.body[0].id, loop.id, body.id, loop.id, body.id]
    assert result.steps[0].note == "x = 1"


def test_comments_and_pass_do_not_take_steps():
    _, result = run_source("# hi\npass\nx = 1\n")
    assert len(result.steps) == 1


def test_actions_are_called_and_their_events_attached():
    calls = []
    events = []

    def step(n=1):
        calls.append(n)
        events.append({"type": "move", "n": n})

    def drain():
        taken = list(events)
        events.clear()
        return taken

    _, result = run_source("step(2)\nstep()\n", actions={"step": step}, drain_events=drain)
    assert calls == [2, 1]
    assert [s.events for s in result.steps] == [
        [{"type": "move", "n": 2}],
        [{"type": "move", "n": 1}],
    ]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("stpe(1)\n", "I don't know `stpe`. Did you mean `step`?"),
        ("x += 1\n", "`x` has no value yet"),
        ("x = 1 / 0\n", "You can't divide by zero."),
        ("x = 'a' + 1\n", "`+` can't combine text and a whole number."),
        ("x = 5\nx(1)\n", "`x` is a whole number, not a command."),
        ("x = int('abc')\n", "`int` can't use these inputs"),
        ("for i in 5:\n    pass\n", "A `for` loop needs something to go through"),
        ("x = 'ab' * 100000\n", "far too long"),
        ("x = -'a'\n", "only works on numbers"),
        ("x = '%d' % 5\n", "`%` with text"),
        ("class Bee:\n    pass\n", "CodeZoo can't run classes yet."),
    ],
)
def test_friendly_errors(source, message):
    _, result = run_source(source, actions={"step": lambda n=1: None})
    assert isinstance(result.error, LearnerError)
    assert message in result.error.message
    assert result.steps[-1].error == result.error.message


def test_error_points_at_the_failing_statement_inside_a_loop():
    parsed, result = run_source("for i in range(3):\n    x = 1 / (i - 2)\n")
    inner = parsed.program.body[0].body[0]
    assert result.error.node_id == inner.id
    assert result.steps[-1].node_id == inner.id


def test_step_limit_stops_long_loops():
    _, result = run_source("for i in range(10 ** 9):\n    pass\n".replace("10 ** 9", "1000000000"))
    assert "more than 10000 steps" in result.error.message


def test_step_limit_is_configurable():
    _, result = run_source("for i in range(10):\n    x = i\n", max_steps=5)
    assert result.error is not None


def test_huge_numbers_are_stopped():
    _, result = run_source("x = 10000000000\nfor i in range(20):\n    x = x * x\n")
    assert "too big" in result.error.message


def test_max_of_a_huge_range_does_not_hang():
    _, result = run_source("print(max(range(1000000000000)))\nprint(min(range(3, 9)))\n")
    assert result.output == ["999999999999", "3"]
