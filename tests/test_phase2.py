"""Phase 2: sensors, new goals, worlds with variants, feelings, limits, `codezoo play`."""

import pytest
from click.testing import CliRunner

from mse_codezoo.cli import main
from mse_codezoo.feelings import feeling
from mse_codezoo.game import level_to_json, run_level, run_to_json, solution_errors
from mse_codezoo.goals import goal_errors, goal_met
from mse_codezoo.interpreter import LearnerError, run
from mse_codezoo.lang_python import parse
from mse_codezoo.levels import Level, find_level, level_files, load_level, load_pack
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.term import StageState, render, replay
from mse_codezoo.world import World

PACK = load_pack("monkey")


def make(tiles, start=(0, 0, "east")):
    return World.from_spec({"tiles": tiles, "start": list(start)}, PACK)


def run_in(world, source):
    parsed = parse(source)
    assert parsed.ok, parsed.diagnostics
    return run(parsed.program, world.actions(), world.drain_events)


# --- sensors -------------------------------------------------------------------------


def test_is_blocked_sees_walls_and_edges():
    world = make([".#", ".."])
    assert world.is_blocked() is True  # rock ahead
    world.turn_right()
    assert world.is_blocked() is False
    world.turn_right()
    assert world.is_blocked() is True  # west edge


def test_item_sensors_return_item_names_or_empty_text():
    world = make(["BC."])
    assert world.item_here() == "banana"
    assert world.item_ahead() == "coconut"
    world.step()
    world.step()
    assert world.item_here() == "" and world.item_ahead() == ""
    senses = [e for e in world.drain_events() if e["type"] == "sense"]
    assert senses[0] == {"type": "sense", "what": "item_here", "result": "banana"}


def test_while_with_a_sensor_walks_to_the_rock():
    world = make(["....#"])
    result = run_in(world, "while not is_blocked():\n    step(1)\n")
    assert result.ok and world.x == 3


def test_endless_while_stops_with_a_friendly_message():
    world = make([".."])
    result = run_in(world, "while is_blocked() == False or True:\n    turn_left()\n")
    assert result.error.kind == "too_many_steps"
    assert "more than" in result.error.message


def test_sensor_without_brackets_is_explained():
    result = run_in(make([".."]), "if is_blocked:\n    step(1)\n")
    assert "Add brackets to ask it: `is_blocked()`" in result.error.message
    result = run_in(make([".."]), "while not item_here:\n    step(1)\n")
    assert "`item_here()`" in result.error.message


# --- friendly errors for the new syntax ---------------------------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("x = 'a' < 1\n", "`<` can't compare text and a whole number."),
        ("x = 'abc'[3]\n", "'abc' has no position 3: it has 3, numbered 0 to 2."),
        ("x = 'abc'[1.5]\n", "Positions in `[ ]` are whole numbers"),
        ("x = (5)[0]\n", "You can't take parts of a whole number"),
        ("x = 'abc'.uper()\n", "Did you mean `.upper()`?"),
        ("x = (5).bit_length()\n", "A whole number has no `.bit_length()` command."),
        ("x = '{0.__class__}'.format(1)\n", "fills only `{}` or numbered `{0}` gaps"),
        ("x = '{:>99999999}'.format(1)\n", "far too long"),
        ("x = f'{1:>99999999}'\n", "far too long"),
        ("x = 'a'.center(10 ** 9)\n", "far too long"),
        ("x = 2 ** 100000\n", "too big"),
        ("x = 2.0 ** 100000\n", "too big"),
        ("x = (-8) ** 0.5\n", "too big"),
        ("x = 'abc'[::0]\n", "step by 0"),
        ("print('a', stop='')\n", "`print` doesn't take a named input `stop=`."),
        ("x = len('a', end='')\n", "doesn't take a named input"),
        ("print('a', end=5)\n", "`end=` needs text"),
        ("x = len(range(10 ** 99))\n", "can't use these inputs"),
        ("x = range\nx()\n", "can't use these inputs"),
    ],
)
def test_friendly_errors_for_new_syntax(source, message):
    result = run_in(make(["."]), source)
    assert isinstance(result.error, LearnerError)
    assert message in result.error.message


def test_type_errors_are_sorted_for_the_report():
    assert run_in(make(["."]), "x = 'a' + 1\n").error.kind == "type"
    assert run_in(make(["."]), "stpe(1)\n").error.kind == "unknown_name"
    assert run_in(make([".#"]), "step(1)\n").error.kind == "bump"


def test_if_steps_note_the_outcome():
    parsed = parse("if 1 < 2:\n    pass\nelse:\n    pass\n")
    result = run(parsed.program)
    assert result.steps[0].note == "-> True"


# --- goals ---------------------------------------------------------------------------


def test_say_goal_one_text_and_sequence():
    world = make(["."])
    world.say("hi")
    world.say(3)
    assert goal_met({"type": "say", "text": "3"}, world)[0]
    assert not goal_met({"type": "say", "text": "4"}, world)[0]
    assert goal_met({"type": "say", "texts": ["hi", "3"]}, world)[0]
    ok, message = goal_met({"type": "say", "texts": ["3", "hi"]}, world)
    assert not ok and 'said "hi, 3"' in message


def test_avoid_and_all_goals():
    world = make(["RB"])
    world.grab()
    ok, message = goal_met({"type": "avoid", "item": "R"}, world)
    assert not ok and "rotten banana" in message
    goal = {
        "type": "all",
        "goals": [{"type": "collect_all", "item": "B"}, {"type": "reach", "at": [0, 0]}],
    }
    assert not goal_met(goal, world)[0]
    world.step()
    world.grab()
    assert not goal_met(goal, world)[0]  # collected, but not back at the start
    assert goal_met({"type": "collect_all", "item": "B", "avoid": "R"}, world)[0] is False


@pytest.mark.parametrize(
    ("goal", "error"),
    [
        ({"type": "say"}, "goal.text"),
        ({"type": "say", "texts": "yum"}, "goal.texts"),
        ({"type": "avoid"}, "goal.item"),
        ({"type": "all", "goals": []}, "goal.goals"),
        ({"type": "all", "goals": [{"type": "nope"}]}, "goal.type"),
    ],
)
def test_goal_errors(goal, error):
    assert any(error in message for message in goal_errors(goal, None))


# --- variants ------------------------------------------------------------------------

TWO_WORLDS = {
    "id": "t-v",
    "module": "test",
    "concepts": ["if"],
    "world": {"tiles": [".B"], "start": [0, 0, "east"]},
    "goal": {"type": "collect_all", "item": "B"},
    "variants": [
        {"tiles": [".R"], "start": [0, 0, "east"], "goal": {"type": "avoid", "item": "R"}}
    ],
}


def test_a_program_must_work_in_every_world():
    level = Level.from_dict(TWO_WORLDS)
    lazy = run_level(level, "step(1)\ngrab()\n")
    assert not lazy.check.solved
    assert lazy.check.message.startswith("It works here, but not in world 2:")
    good = run_level(level, "step(1)\nif item_here() == 'banana':\n    grab()\n")
    assert good.check.solved


def test_run_shows_the_chosen_world():
    level = Level.from_dict(TWO_WORLDS)
    run_ = run_level(level, "step(1)\ngrab()\n", variant=1)
    data = run_to_json(run_)
    assert data["variant"] == 1
    assert data["world"]["collected"] == {"R": 1}
    assert run_level(level, "pass\n", variant=7).variant == 0  # unknown -> the main world


def test_level_json_lists_every_world():
    data = level_to_json(find_level("m05-l04"))
    assert len(data["worlds"]) == 2 and len(data["goals"]) == 2
    assert data["worlds"][1]["walls"] == [[1, 1]]
    assert data["pack"]["actions"]["is_blocked"] == "is_blocked"


def test_variant_validation(tmp_path):
    from mse_codezoo.levels import validate_level

    bad = dict(TWO_WORLDS, variants=[{"tiles": ["?"], "start": [0, 0, "east"]}, "x"])
    path = tmp_path / "l01.json"
    import json

    path.write_text(json.dumps(bad), encoding="utf-8")
    errors = validate_level(path).errors
    assert any(e.startswith("variant 2: unknown tile") for e in errors)
    assert "variant 3: must be a world object" in errors


def test_starter_programs_still_need_fixing():
    for path in level_files():
        level = load_level(path)
        if level.starter:
            assert not run_level(level, level.starter).check.solved, level.id


def test_every_condition_level_needs_its_condition():
    """Without an `if`, a program that solves world 1 fails another world."""
    for path in level_files():
        level = load_level(path)
        if len(level.worlds()) > 1:
            assert solution_errors(level) == [], level.id


# --- feelings ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "mood"),
    [
        ({"parsed": False, "solved": False, "stars": 0, "error_kind": "syntax"}, "confused"),
        ({"parsed": True, "solved": True, "stars": 3, "error_kind": None}, "proud"),
        ({"parsed": True, "solved": True, "stars": 2, "error_kind": None}, "happy"),
        ({"parsed": True, "solved": False, "stars": 0, "error_kind": "bump"}, "oops"),
        ({"parsed": True, "solved": False, "stars": 0, "error_kind": "too_many_steps"}, "dizzy"),
        ({"parsed": True, "solved": False, "stars": 0, "error_kind": "type"}, "confused"),
        ({"parsed": True, "solved": False, "stars": 0, "error_kind": None}, "puzzled"),
    ],
)
def test_feelings(kwargs, mood):
    result = feeling(animal="monkey", **kwargs)
    assert result.mood == mood
    assert result.text and result.face


def test_runs_carry_a_feeling():
    data = run_to_json(run_level(find_level("m01-l01"), "step(4)\ngrab()\n"))
    assert data["feeling"]["mood"] == "proud"
    broken = run_to_json(run_level(find_level("m01-l07"), find_level("m01-l07").starter))
    assert broken["feeling"]["mood"] == "puzzled"
    assert "bug" in broken["feeling"]["text"]


# --- terminal stage ------------------------------------------------------------------


def test_terminal_replay_follows_the_events():
    level = find_level("m01-l03")
    data = run_to_json(run_level(level, "turn_right()\nstep(1)\nturn_left()\nstep(2)\n"))
    shown = []
    state = replay(
        level_to_json(level)["world"],
        data["steps"],
        [],
        echo=shown.append,
        color=False,
        animate=False,
    )
    assert state.position == (2, 1)
    assert "| . # B |\n| . . > |" in shown[-1]


def test_terminal_render_shows_bumps_and_speech():
    state = StageState.from_json(level_to_json(find_level("m01-l01"))["world"])
    state.apply({"type": "say", "text": "Yum!"})
    assert render(state, color=False).startswith('  "Yum!"')
    state.apply({"type": "bump", "at": [0, 0]})
    assert "| * " in render(state, color=False)
    assert "\x1b[" in render(state, color=True)


# --- codezoo play --------------------------------------------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def play(*args, keys):
    return CliRunner().invoke(main, ["play", *args], input=keys)


def test_play_runs_the_program_file(home):
    folder = home / "play"
    folder.mkdir(parents=True)
    (folder / "m01-l01.py").write_text("step(4)\ngrab()\n", encoding="utf-8")
    result = play("--level", "m01-l01", keys="r\nq\n")
    assert result.exit_code == 0, result.output
    assert "Level m01-l01: One banana" in result.output
    assert "The monkey collected every banana!" in result.output
    assert "Bye!" in result.output


def test_play_creates_a_file_shows_hints_and_moves_on(home):
    result = play("--level", "m05-l04", keys="h\nh\nh\n2\nn\nq\n")
    assert result.exit_code == 0, result.output
    created = (home / "play" / "m05-l04.py").read_text(encoding="utf-8")
    assert created.startswith("# Level m05-l04: Rock ahead?")
    assert "Hint 2:" in result.output
    assert "World 2 of 2" in result.output
    assert "Level m05-l05" in result.output


def test_play_saves_progress_and_starts_at_the_first_unsolved_level(home):
    store = ProfileStore(home)
    store.add("Ema", "fox")
    folder = home / "play"
    folder.mkdir(parents=True)
    (folder / "m01-l01.py").write_text("step(4)\ngrab()\n", encoding="utf-8")
    assert play("--profile", "Ema", keys="r\nq\n").exit_code == 0
    assert store.progress("Ema")["levels"]["m01-l01"]["stars"] == 3
    again = play("--profile", "Ema", keys="q\n")
    assert "Level m01-l02" in again.output


def test_play_respects_the_daily_limit(home):
    store = ProfileStore(home)
    store.add("Ema", "fox")
    store.update_parent(daily_minutes=1)
    store.add_time("Ema", 61)
    result = play("--profile", "Ema", keys="r\n")
    assert "That's all for today!" in result.output


def test_play_in_slovak(home):
    result = CliRunner().invoke(main, ["--lang", "sk", "play", "--level", "m01-l01"], input="q\n")
    assert "Level m01-l01: Jeden banán" in result.output
    assert "opička" in result.output


def test_play_unknown_level(home):
    result = play("--level", "nope", keys="q\n")
    assert result.exit_code != 0 and "No level called" in result.output


def test_trace_shows_sensor_questions(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("if is_blocked():\n    turn_left()\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["run", "m05-l04", str(program), "--trace"])
    assert "asks is_blocked() -> True" in result.output


def test_levels_show_lists_other_worlds():
    result = CliRunner().invoke(main, ["levels", "show", "m05-l08"])
    assert 'World 2: say "crack", then "hmm", then "yum"' in result.output


def test_check_prints_the_feeling(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("step(4)\ngrab()\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", "m01-l01", str(program)])
    assert "proud of you" in result.output
