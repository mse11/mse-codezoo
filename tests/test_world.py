import pytest

from mse_codezoo.interpreter import LearnerError
from mse_codezoo.world import Pack, World


def make(tiles, start=(0, 0, "east"), pack=None):
    spec = {"tiles": tiles, "start": list(start)}
    return World.from_spec(spec, pack) if pack else World.from_spec(spec)


def test_step_turn_and_grab():
    world = make(["..", ".B"])
    world.step()
    world.turn_right()
    world.step(1)
    world.grab()
    assert (world.x, world.y, world.facing) == (1, 1, "south")
    assert world.remaining("B") == 0
    assert world.collected == {"B": 1}
    assert [e["type"] for e in world.drain_events()] == ["move", "turn", "move", "grab"]
    assert world.drain_events() == []


def test_turning_goes_round_both_ways():
    world = make(["."])
    for expected in ("north", "west", "south", "east"):
        world.turn_left()
        assert world.facing == expected
    world.turn_right()
    assert world.facing == "south"


def test_walls_and_edges_bump():
    world = make([".#"])
    with pytest.raises(LearnerError, match="walked into a wall"):
        world.step()
    world.turn_left()
    with pytest.raises(LearnerError, match="edge of the jungle"):
        world.step()
    assert world.drain_events()[-1]["type"] == "bump"


def test_bump_stops_partway_through_a_long_step():
    world = make(["...#"])
    with pytest.raises(LearnerError):
        world.step(5)
    assert world.x == 2


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "3"])
def test_step_needs_a_positive_whole_number(bad):
    with pytest.raises(LearnerError, match="whole number"):
        make([".."]).step(bad)


def test_grab_on_empty_square_is_not_an_error():
    world = make(["."])
    world.grab()
    assert world.drain_events() == [{"type": "grab", "at": [0, 0], "item": None, "near": "none"}]


def test_render_shows_animal_walls_and_items():
    assert make([".#B"], start=(0, 0, "north")).render() == "^#B"


def test_pack_renames_actions_and_messages():
    pack = Pack("penguin", "penguin", "ice field", actions={"grab": "catch"}, items={"B": "fish"})
    world = make([".B"], pack=pack)
    assert "catch" in world.actions() and "grab" not in world.actions()
    world.turn_left()
    with pytest.raises(LearnerError, match="penguin reached the edge of the ice field"):
        world.step()


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"tiles": [], "start": [0, 0, "east"]}, "non-empty"),
        ({"tiles": ["..", "."], "start": [0, 0, "east"]}, "same length"),
        ({"tiles": [".."], "size": [3, 1], "start": [0, 0, "east"]}, "does not match"),
        ({"tiles": [".?"], "start": [0, 0, "east"]}, "unknown tile"),
        ({"tiles": [".."], "start": [0, 0, "up"]}, "world.start must be"),
        ({"tiles": ["#."], "start": [0, 0, "east"]}, "on a wall"),
        ({"tiles": [".."], "start": [5, 0, "east"]}, "outside the grid"),
    ],
)
def test_bad_world_specs_are_rejected(spec, message):
    with pytest.raises(ValueError, match=message):
        World.from_spec(spec)


def test_tiles_may_be_one_string_with_newlines():
    assert World.from_spec({"tiles": "..\n.B", "start": [0, 0, "east"]}).remaining() == 1
