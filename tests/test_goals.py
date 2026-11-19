from mse_codezoo.goals import check, count_lines, used_node_types
from mse_codezoo.interpreter import run
from mse_codezoo.lang_python import parse
from mse_codezoo.world import World

GOAL = {"type": "collect_all", "item": "B"}


def play(source, tiles=(".BBB",), goal=GOAL, constraints=None):
    world = World.from_spec({"tiles": list(tiles), "start": [0, 0, "east"]})
    program = parse(source).program
    result = run(program, world.actions(), world.drain_events)
    return check(goal, constraints or {}, program, result, world)


LOOP = "for i in range(3):\n    step(1)\n    grab()\n"
LONG = "step(1)\ngrab()\nstep(1)\ngrab()\nstep(1)\ngrab()\n"


def test_three_stars_for_a_short_loop():
    outcome = play(LOOP, constraints={"maxLines": 3, "mustUse": ["For"]})
    assert outcome.solved
    assert outcome.earned == 3
    assert outcome.message == "The monkey collected every banana!"


def test_long_solution_loses_line_and_concept_stars():
    outcome = play(LONG, constraints={"maxLines": 3, "mustUse": ["For"]})
    assert outcome.solved
    assert outcome.earned == 1
    assert outcome.stars[1].label == "3 lines or fewer (used 6)"


def test_unsolved_earns_nothing_and_says_what_is_left():
    outcome = play("step(1)\ngrab()\n", constraints={"maxLines": 3})
    assert not outcome.solved
    assert outcome.earned == 0
    assert outcome.message == "2 bananas still to collect."


def test_runtime_error_is_the_message():
    outcome = play("step(9)\n")
    assert not outcome.solved
    assert outcome.message.startswith("Bump!")


def test_no_constraints_means_all_stars_when_solved():
    assert play(LONG).earned == 3


def test_reach_goal():
    outcome = play("step(2)\n", tiles=("...",), goal={"type": "reach", "at": [2, 0]})
    assert outcome.solved and outcome.message == "The monkey got there!"
    assert not play("step(1)\n", tiles=("...",), goal={"type": "reach", "at": [2, 0]}).solved


def test_count_lines_ignores_comments_and_layout():
    assert count_lines(parse("# note\nstep(1)  # inline\n\n\ngrab()\n").program) == 2


def test_used_node_types():
    assert {"For", "Call", "Comment"} <= used_node_types(parse("# hi\n" + LOOP).program)
