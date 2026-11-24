"""Phase 8, step G0: game mode. A program sets up a world, then handlers run on every tick."""

import time

import pytest

from mse_codezoo import gamemode, webbuild
from mse_codezoo.gamemode import BROKEN, LOST, OVER, PLAYING, WON, Game, GameSpec, play
from mse_codezoo.i18n import use_lang
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import ApiError, dispatch

WORLD = {"tiles": ["B....", ".....", "....B"], "start": [2, 1, "east"]}


def spec(**extra):
    data = {"id": "test-game", "title": {"en": "Test", "sk": "Test"}, "world": WORLD} | extra
    return GameSpec.from_dict(data)


def game(source, keys=(), **extra):
    return play(spec(**extra), source, [list(k) for k in keys])


# --- bundled games ---------------------------------------------------------------------


def test_every_bundled_game_loads_and_its_starter_plays():
    games = gamemode.all_games()
    assert games, "content/games has no games"
    for found in games:
        assert found.title.get("sk"), f"{found.id} needs a Slovak title"
        played = play(found, found.starter, [["left"], [], ["up"]] * 20)
        assert played.status in (PLAYING, WON, LOST), (found.id, played.message)
        assert played.error is None, (found.id, played.message)


def test_game_json_draws_the_world_in_the_language():
    found = gamemode.find_game("collect-guard")
    with use_lang("sk"):
        data = gamemode.game_to_json(found)
    assert data["title"] == "Banány a strážca"
    assert data["help"][0].startswith("Hýb sa")
    assert data["world"]["position"] == [4, 4]
    assert data["keys"] == ["up", "down", "left", "right", "space"]


@pytest.mark.parametrize(
    "bad",
    [
        {"world": None},
        {"rules": {"win": "everything"}},
        {"rules": {"win": {"score": 0}}},
        {"max_ticks": 0},
        {"animal": "dragon"},
        {"world": {"tiles": ["..#"], "start": [2, 0, "east"]}},
    ],
)
def test_bad_game_files_are_refused(bad):
    data = {"id": "bad", "title": "Bad", "world": WORLD} | bad
    with pytest.raises(ValueError):
        GameSpec.from_dict(data)


# --- keys, ticks, critters -------------------------------------------------------------


def test_without_on_key_the_arrows_move_the_animal_and_bumps_dont_crash():
    played = game("", [["up"], ["up"], ["up"], ["left"]])
    assert played.status == PLAYING
    assert played.where() == (1, 0)  # the second and third "up" bumped the edge
    assert played.tick_count == 4


def test_handlers_run_in_order_every_tick():
    source = (
        "log = []\n"
        "def on_key(key):\n    log.append(key)\n"
        "def on_tick():\n    log.append(ticks())\n"
        "    if ticks() == 2:\n        print(log)\n"
    )
    played = game(source, [["space", "left"], []])
    assert played.output == ["['space', 'left', 1, 2]"]
    assert played.where() == (2, 1)  # on_key took over the arrows


def test_critters_patrol_with_their_own_on_tick():
    source = (
        "class Guard(Critter):\n"
        "    def on_tick(self):\n"
        "        if self.wall_ahead():\n            self.turn_around()\n"
        "        else:\n            self.step()\n"
        "g = Guard(0, 2, 'east')\n"
        "def on_tick():\n    if ticks() == 6:\n        print(g.x, g.y, g.facing, g.kind)\n"
    )
    played = game(source, [[]] * 6)
    # the program's on_tick runs before the critters move: it sees the end of tick 5
    assert played.output == ["4 2 west guard"]


def test_a_critter_keeps_its_place_in_the_game_not_on_the_object():
    source = "class Guard(Critter):\n    pass\ng = Guard(1, 1)\ng.x = 4\n"
    played = game(source)
    assert played.status == BROKEN
    assert played.state()["critters"][0]["at"] == [1, 1]


def test_a_critter_without_super_init_gets_a_kind_message():
    source = (
        "class Guard(Critter):\n    def __init__(self, x):\n        self.where = x\n"
        "g = Guard(1)\ng.step()\n"
    )
    played = game(source)
    assert played.status == BROKEN
    assert "super().__init__(x, y)" in played.message


def test_critters_cant_start_inside_walls_or_go_through_each_other():
    played = game("class G(Critter):\n    pass\nG(9, 9)\n")
    assert played.status == BROKEN and "isn't open" in played.message
    source = (
        "class G(Critter):\n    pass\na = G(0, 1, 'east')\nb = G(1, 1, 'west')\n"
        "print(a.step(), b.step())\n"
    )
    assert game(source).output == ["False False"]


def test_removed_critters_leave_the_game():
    made = "class G(Critter):\n    pass\na = G(0, 1)\nb = G(0, 2)\n"
    source = made + "a.remove()\nprint(len(critters()))\n"
    played = game(source)
    assert played.output == ["1"]
    assert [c["at"] for c in played.state()["critters"]] == [[0, 2]]


# --- items, touches, rules -------------------------------------------------------------


def test_on_item_and_collect_all_wins():
    source = "def on_item(item):\n    grab()\n    score.add(1)\n"
    top = WORLD | {"start": [2, 0, "west"]}
    played = game(source, [["left"], ["left"]], rules={"win": "collect_all"}, world=top)
    assert played.score.value == 1  # the banana at (0, 0)
    played = game(
        source,
        [["left"], ["left"]] + [["right"]] * 4 + [["down"], ["down"]],
        rules={"win": "collect_all"},
        world=top,
    )
    assert played.status == WON
    assert played.message == "Every item collected!"


def test_caught_loses_unless_on_touch_decides():
    critter = "class G(Critter):\n    pass\ng = G(3, 1, 'west')\n"
    assert game(critter, [["right"]], rules={"caught": True}).status == LOST
    source = critter + "def on_touch(c):\n    score.add(5)\n    c.remove()\n"
    played = game(source, [["right"], []], rules={"caught": True})
    assert played.status == PLAYING and played.score.value == 5
    assert played.state()["critters"] == []


def test_score_and_survive_rules_and_time_up():
    assert game("score.add(3)\n", [[]], rules={"win": {"score": 3}}).status == WON
    assert game("", [[]] * 5, rules={"win": {"survive": 5}}).status == WON
    played = game("", [[]] * 5, max_ticks=3)
    assert played.status == OVER and played.tick_count == 3


def test_win_and_lose_from_the_program():
    played = game("def on_tick():\n    if ticks() == 2:\n        win('Yay')\n", [[]] * 5)
    assert (played.status, played.message, played.tick_count) == (WON, "Yay", 2)
    assert game("lose()\n", [[]]).status == LOST


def test_score_takes_whole_numbers_only():
    played = game("score.add('lots')\n")
    assert played.status == BROKEN
    assert "whole numbers" in played.message


# --- safety: the game never freezes or crashes the engine -------------------------------


def test_an_endless_loop_in_a_handler_tires_the_game_out():
    played = game("def on_tick():\n    while True:\n        pass\n", [[]] * 3)
    assert played.status == BROKEN
    assert played.tick_count == 1
    assert "took more than 1000 steps in one tick" in played.message
    assert played.error_json()["line"] == 2


def test_errors_in_handlers_point_at_the_line():
    played = game("def on_key(key):\n    x = 1 / 0\n", [["up"]])
    assert played.status == BROKEN
    assert played.error_json()["line"] == 2
    assert "divide by zero" in played.message


def test_syntax_errors_and_async_handlers_stop_before_playing():
    played = game("def on_tick(:\n")
    assert played.status == BROKEN and played.parsed.errors
    played = game("async def on_tick():\n    pass\n")
    assert played.status == BROKEN and "plain function" in played.message


def test_finished_games_ignore_more_ticks():
    played = game("lose()\n")
    played.tick(["up"])
    assert played.tick_count == 0 and played.where() == (2, 1)


# --- deterministic: same program, seed and keys give the same game -----------------------


def test_games_replay_exactly_from_their_keys():
    source = (
        "import random\n"
        "class G(Critter):\n"
        "    def on_tick(self):\n"
        "        self.face(random.choice(['up', 'down', 'left', 'right']))\n"
        "        self.step()\n"
        "gs = [G(0, 1), G(4, 1)]\n"
    )
    keys = [["left"], [], ["up"], ["right"], [], []] * 10
    first = game(source, keys)
    again = play(spec(), source, first.inputs, seed=0)
    assert first.state() == again.state()
    other = play(spec(), source, first.inputs, seed=1)
    assert other.state() != first.state()


def test_a_tick_is_fast_enough_for_a_slow_tablet():
    """G0 measurement: about 7 ticks a second are needed; CPython does thousands. Pyodide
    is slower (measured in the browser, see IMPLEMENTATION_PLAN.md), so keep a big margin."""
    source = (
        "class G(Critter):\n"
        "    def on_tick(self):\n"
        "        if self.wall_ahead():\n            self.turn_around()\n"
        "        else:\n            self.step()\n"
        "gs = [G(0, 0), G(4, 0, 'west'), G(0, 2), G(4, 2, 'west'), G(1, 1)]\n"
    )
    played = Game(spec(), source)
    played.start()
    started = time.perf_counter()
    for _ in range(200):
        played.tick([])
    per_tick = (time.perf_counter() - started) / 200
    assert played.status == PLAYING
    assert per_tick < 0.01


# --- the API ---------------------------------------------------------------------------


def test_api_starts_ticks_and_stops_a_game(tmp_path):
    store = ProfileStore(tmp_path)
    listed = dispatch("GET", "/api/games", {}, {}, store)
    assert {"id": "collect-guard"}.items() <= listed[0].items()
    drawn = dispatch("GET", "/api/games/collect-guard", {}, {}, store)
    started = dispatch(
        "POST", "/api/game/start", {}, {"game": "collect-guard", "source": drawn["starter"]}, store
    )
    assert started["state"]["status"] == PLAYING
    assert started["handlers"] == ["on_item", "on_key"]
    session = started["session"]
    ticked = dispatch("POST", "/api/game/tick", {}, {"session": session, "keys": ["left"]}, store)
    assert ticked["state"]["tick"] == 1
    assert ticked["state"]["animal"]["at"] == [3, 4]
    assert any(event["type"] == "move" for event in ticked["events"])
    dispatch("POST", "/api/game/stop", {}, {"session": session}, store)
    with pytest.raises(ApiError):
        dispatch("POST", "/api/game/tick", {}, {"session": session}, store)


def test_api_refuses_bad_requests(tmp_path):
    store = ProfileStore(tmp_path)
    with pytest.raises(ApiError):
        dispatch("GET", "/api/games/../secret", {}, {}, store)
    with pytest.raises(ApiError):
        dispatch("POST", "/api/game/start", {}, {"game": "nope", "source": ""}, store)
    with pytest.raises(ApiError):
        dispatch("POST", "/api/game/start", {}, {"gameData": {"id": "x"}, "source": ""}, store)
    started = dispatch("POST", "/api/game/start", {}, {"game": "collect-guard"}, store)
    with pytest.raises(ApiError):
        dispatch("POST", "/api/game/tick", {}, {"session": started["session"], "keys": "up"}, store)


def test_sessions_forget_the_oldest_games():
    sessions = gamemode.Sessions(limit=2)
    ids = [sessions.add(Game(spec(), "")) for _ in range(3)]
    assert sessions.get(ids[0]) is None
    assert sessions.get(ids[2]) is not None


def test_the_offline_build_has_the_game_page():
    assert "game.html" in webbuild.PAGES


def test_the_game_page_has_a_3d_stage_and_keeps_2d():
    """Games draw on the zoo's 3D stage (loaded only when picked) or the flat board."""
    web = webbuild.WEB_DIR
    page = (web / "game.html").read_text(encoding="utf-8")
    assert 'id="view-2d"' in page and 'id="view-3d"' in page
    script = (web / "game.js").read_text(encoding="utf-8")
    assert 'import("./stage3d.js")' in script  # not loaded for 2D
    assert "webglAvailable()" in script  # no WebGL: the flat board
    stage = (web / "stage3d.js").read_text(encoding="utf-8")
    for method in ("loadGame(game)", "showGame(state", "bumpGame(target)"):
        assert method in stage
    for kind in ("makeGuard", "makeGhost", "makeBeetle"):
        assert f"function {kind}()" in stage or f"function {kind}(" in stage
