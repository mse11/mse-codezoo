"""Phase 8, steps G1-G3: make a game alone (templates, rounds, twists, the playtest bot),
the world editor and sharing (objects with scripts, building with code, share links,
class shares), and playing together on the classroom hub (several animals, lockstep,
server-sent events, emoji only)."""

import json
import random
import threading
import time
import urllib.error
import urllib.request

import pytest

from mse_codezoo import gamemode, gamerooms
from mse_codezoo.classes import ClassError, ClassStore
from mse_codezoo.gamemode import BROKEN, LOST, PLAYING, WON, Game, GameError, GameSpec, play
from mse_codezoo.gamerooms import MultiGame, RoomError, Rooms, replay
from mse_codezoo.hub import Hub
from mse_codezoo.i18n import use_lang
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import ApiError, CodeZooServer, dispatch, dispatch_json

WORLD = {"tiles": ["B....", ".....", "....B"], "start": [2, 1, "east"]}
MOVE = 'def on_key(key):\n    if key != "space":\n        go(key)\n'


def spec(**extra):
    data = {"id": "test-game", "title": {"en": "Test", "sk": "Test"}, "world": WORLD} | extra
    return GameSpec.from_dict(data)


def started(source, **extra):
    game = Game(spec(**extra), source)
    game.start()
    return game


@pytest.fixture
def rooms(monkeypatch):
    """Rooms that tick only when a test says so (no thread, no clock)."""
    fresh = Rooms(auto=False)
    monkeypatch.setattr(gamerooms, "ROOMS", fresh)
    return fresh


# --- G1: templates and lesson rounds ------------------------------------------------------


def test_the_four_templates_come_in_lesson_order():
    games = [g for g in gamemode.all_games() if not g.id.startswith("bug-")]  # bug hunts apart
    assert [g.template for g in games] == ["collect", "dodge", "chase", "maze"]
    for found in games:
        assert found.title.get("sk"), found.id
        assert len(found.rounds) == 5, found.id
        assert found.rounds[0]["needs"] == ["on_key", "go"]
        assert found.rounds[-1].get("twist"), f"{found.id}: the last round is the twist card"
        for round_ in found.rounds:
            assert round_["title"].get("sk") and round_["goal"].get("sk"), found.id
        assert found.lesson.startswith("#"), found.id


def test_every_template_starter_is_fair_for_the_bots():
    """The playtest bot is the templates' own check: they start, nothing breaks, and
    some bots win but not all of them in a few ticks."""
    for found in gamemode.all_games():
        report = gamemode.playtest(found, found.starter, games=12)
        assert report["broken"] == 0, (found.id, report["messages"])
        assert 0 < report["won"], (found.id, report["messages"])
        assert report["unreachable"] == [], found.id


def test_the_lesson_start_has_no_round_done_and_the_hints_complete_them():
    for found in gamemode.all_games():
        lesson = Game(found, found.lesson)
        lesson.start()
        features = set(lesson.features())
        done = [r for r in found.rounds if r["needs"] and gamemode.round_done(r["needs"], features)]
        assert not done, found.id
        # every round's hint, added to the starter, makes that round count
        for round_ in found.rounds:
            if round_.get("twist"):
                continue
            hint = round_.get("hint", {}).get("en", "")
            game = Game(found, found.starter + "\n\n" + hint)
            game.start()
            assert gamemode.round_done(round_["needs"], game.features()), (
                found.id,
                round_["title"]["en"],
            )


def test_features_name_handlers_critters_and_names():
    game = started(
        "class G(Critter):\n    def on_tick(self):\n        self.step()\n"
        "a = G(0, 1)\nb = G(4, 1)\n" + MOVE + "def on_item(item):\n    grab()\n    score.add(1)\n"
    )
    features = set(game.features())
    assert {"on_key", "on_item", "critter", "critters2", "critter_tick"} <= features
    assert {"score", "grab", "go"} <= features
    half_typed = started("def on_key(key):\n    go(key\n")
    assert "on_key" in half_typed.features() or half_typed.status == BROKEN


def test_rounds_and_templates_are_checked():
    with pytest.raises(GameError, match="template"):
        spec(template="racing")
    with pytest.raises(GameError, match="needs"):
        spec(rounds=[{"title": "A", "goal": "B", "needs": ["not a name!"]}])
    with pytest.raises(GameError, match="round 1"):
        spec(rounds=["move"])
    found = spec(
        rounds=[{"title": {"en": "Move", "sk": "Hýb sa"}, "goal": "Go", "needs": ["on_key"]}]
    )
    with use_lang("sk"):
        assert found.rounds_text()[0]["title"] == "Hýb sa"
    assert found.rounds_text()[0]["goal"] == "Go"


def test_twist_cards_say_what_makes_them_done():
    cards = gamemode.twists()
    assert {card["id"] for card in cards} == {
        "speed-up",
        "second-critter",
        "power-up",
        "secret-door",
    }
    for card in cards:
        assert card["needs"] and card["code"] and card["emoji"]
    with use_lang("sk"):
        assert gamemode.twists()[0]["title"] == "Zrýchlenie"


def test_game_json_carries_rounds_twists_and_the_file():
    drawn = gamemode.game_to_json(gamemode.find_game("chase-frogs"))
    assert len(drawn["rounds"]) == 5 and drawn["twists"]
    assert drawn["lesson"] and drawn["spec"]["id"] == "chase-frogs"
    assert drawn["world"]["objects"][0]["class"] == "Frog"
    again = GameSpec.from_dict(drawn["spec"])
    assert again.to_dict() == drawn["spec"]


def test_game_code_works_with_every_animal():
    """The penguin's grab is called `catch`; a game's `grab()` still works for it."""
    found = gamemode.find_game("collect-guard")
    game = Game(found, found.starter, animal="penguin")
    game.start()
    for _ in range(4):
        game.tick(["left"])
    assert game.status == PLAYING and game.score.value == 1


# --- G1: the playtest bot ------------------------------------------------------------------


def test_playtest_is_deterministic():
    found = gamemode.find_game("collect-guard")
    first = gamemode.playtest(found, found.starter, games=9)
    again = gamemode.playtest(found, found.starter, games=9)
    assert first == again
    assert first["played"] == 9 and first["won"] + first["lost"] + first["playing"] == 9


def test_playtest_finds_items_nobody_can_reach():
    walled = {"tiles": ["B#...", "##...", "....B"], "start": [2, 1, "east"]}
    report = gamemode.playtest(
        spec(world=walled, rules={"win": "collect_all"}),
        MOVE + "def on_item(item):\n    grab()\n",
        games=3,
    )
    assert report["unreachable"] == [[0, 0]]
    assert any("(0, 0)" in m["text"] for m in report["messages"])
    assert report["won"] == 0


def test_playtest_says_when_nobody_can_win_or_everyone_wins_fast():
    no_rule = gamemode.playtest(spec(), MOVE, games=3)
    assert any("way to win" in m["text"] for m in no_rule["messages"])
    easy = gamemode.playtest(spec(rules={"win": {"survive": 3}}), MOVE, games=3)
    assert easy["won"] == 3
    assert any("too easy" in m["text"] for m in easy["messages"])


def test_playtest_reports_a_broken_game_with_its_line():
    report = gamemode.playtest(
        spec(rules={"win": {"survive": 50}}), "def on_tick():\n    go(3)\n", games=3
    )
    assert report["broken"] == 3
    assert report["error"]["line"] == 2
    assert report["messages"][0]["kind"] == "err"
    setup = gamemode.playtest(spec(), "x = 1 / 0\n", games=3)
    assert setup["played"] == 0 and setup["messages"][0]["kind"] == "err"


def test_playtest_says_when_the_critters_catch_everyone():
    source = (
        "class Hunter(Critter):\n    def on_tick(self):\n        x, y = where()\n"
        "        if x > self.x:\n            self.face('east')\n"
        "        elif x < self.x:\n            self.face('west')\n"
        "        elif y > self.y:\n            self.face('south')\n"
        "        else:\n            self.face('north')\n"
        "        self.step()\n\nfor x in range(5):\n    Hunter(x, 0)\n    Hunter(x, 2)\n"
    )
    report = gamemode.playtest(
        spec(
            world={"tiles": [".....", ".....", "....."], "start": [2, 1, "east"]},
            rules={"win": {"survive": 80}, "caught": True},
        ),
        source + MOVE,
        games=6,
    )
    assert report["won"] == 0 and report["lost"] > 3
    assert any("caught" in m["text"] for m in report["messages"])


def test_playtest_stops_on_a_slow_device():
    found = gamemode.find_game("dodge-bees")
    report = gamemode.playtest(found, found.starter, games=50, seconds=0.0001)
    assert report["played"] < 50
    assert any("slow" in m["text"] for m in report["messages"])


# --- G2: objects with attached scripts --------------------------------------------------------


def test_objects_are_made_from_the_programs_class():
    world = WORLD | {
        "objects": [{"at": [0, 1], "class": "Guard", "facing": "south", "kind": "ghost"}]
    }
    game = started(
        "class Guard(Critter):\n    def on_tick(self):\n        self.step()\n", world=world
    )
    assert game.state()["critters"] == [{"id": 1, "at": [0, 1], "facing": "south", "kind": "ghost"}]
    assert "object" in game.features()
    game.tick([])
    assert game.state()["critters"][0]["at"] == [0, 2]


def test_an_object_without_its_class_stands_still_with_a_kind_note():
    world = WORLD | {"objects": [{"at": [4, 1], "class": "Bee"}]}
    game = Game(spec(world=world), "")
    result = game.start()
    assert game.state()["critters"][0]["at"] == [4, 1]
    assert any("class Bee(Critter)" in note for note in result.notes)
    assert "object" not in game.features()


def test_an_objects_own_init_runs_and_its_errors_show():
    world = WORLD | {"objects": [{"at": [4, 1], "class": "Bee"}]}
    game = started(
        "class Bee(Critter):\n    def __init__(self, x, y):\n"
        "        super().__init__(x, y)\n        self.speed = 2\n",
        world=world,
    )
    assert game.status == PLAYING and len(game.state()["critters"]) == 1
    broken = started("class Bee(Critter):\n    def __init__(self):\n        pass\n", world=world)
    assert broken.status == BROKEN


@pytest.mark.parametrize(
    "objects, problem",
    [
        ([{"at": [9, 9], "class": "G"}], "outside"),
        ([{"at": [2, 1], "class": "G"}], "open square"),  # the start
        ([{"at": [0, 1], "class": "G"}, {"at": [0, 1], "class": "G"}], "two objects"),
        ([{"at": [0, 1], "class": "not a class"}], "class name"),
        ([{"at": [0, 1], "class": "G", "facing": "up-ish"}], "direction"),
        ([{"at": [0], "class": "G"}], "square"),
        ("G", "list"),
    ],
)
def test_bad_objects_are_refused(objects, problem):
    with pytest.raises(GameError, match=problem):
        spec(world=WORLD | {"objects": objects})


# --- G2: building with code ---------------------------------------------------------------


def test_build_puts_and_clears_squares():
    game = started(
        "for x in range(3):\n    build.block(x, 2, 'stone')\n"
        "build.block(4, 0, 'water')\nbuild.item(1, 1)\nbuild.clear(4, 2)\n"
        "print(build.what(0, 2), build.what(4, 0), build.what(1, 1), build.what(3, 1))\n"
    )
    state = game.state()
    assert [[0, 2], [1, 2], [2, 2]] == state["walls"]
    assert [4, 0, "~"] in state["terrain"]
    assert [1, 1, "B"] in state["items"] and [4, 2, "B"] not in state["items"]
    assert game.output == ["stone water banana "]


def test_build_wont_bury_the_animal_and_checks_its_inputs():
    game = started("build.block(2, 1, 'stone')\n")
    assert game.state()["walls"] == []
    assert game.status == PLAYING
    for bad in (
        "build.block(1, 1, 'lava')",
        "build.block(9, 9)",
        "build.item(1, 1, 'pizza')",
        "build.block('a', 1)",
    ):
        assert started(bad + "\n").status == BROKEN, bad


def test_build_sends_tile_events_and_counts_new_items_for_collect_all():
    found = spec(
        world={"tiles": [".....", ".....", "....."], "start": [2, 1, "east"]},
        rules={"win": "collect_all"},
    )
    game = Game(found, "build.item(3, 1)\n" + MOVE + "def on_item(item):\n    grab()\n")
    result = game.start()
    assert {"type": "tile", "at": [3, 1], "tile": "B"} in result.events
    game.tick(["right"])
    assert game.status == WON


def test_a_secret_door_opens_from_a_handler():
    walled = {"tiles": ["..#..", "..#..", "..#.B"], "start": [0, 1, "east"]}
    source = MOVE + "def on_tick():\n    if ticks() == 2:\n        build.clear(2, 1)\n"
    game = play(spec(world=walled), source, [["right"], ["right"], ["right"], ["right"]])
    assert game.world.x == 3


# --- G2: sharing -----------------------------------------------------------------------------


def test_the_api_previews_and_tests_a_game_from_the_editor(tmp_path):
    store = ProfileStore(tmp_path)
    data = gamemode.find_game("maze-ghost").to_dict()
    data["world"]["tiles"][4] = "......###"
    drawn = dispatch("POST", "/api/game/preview", {}, {"gameData": data}, store)
    assert [6, 4] in drawn["world"]["walls"]
    report = dispatch(
        "POST",
        "/api/game/test",
        {},
        {"gameData": data, "source": data["starter"], "games": 3},
        store,
    )
    assert report["played"] == 3
    started_ = dispatch(
        "POST", "/api/game/start", {}, {"gameData": data, "source": data["starter"]}, store
    )
    assert started_["features"] and started_["state"]["walls"]
    with pytest.raises(ApiError):
        dispatch(
            "POST",
            "/api/game/preview",
            {},
            {"gameData": {**data, "world": {"tiles": ["#"], "start": [0, 0, "east"]}}},
            store,
        )
    listed = dispatch("GET", "/api/games", {}, {}, store)
    assert listed[0]["animal"] == "monkey"


def test_a_game_is_shared_with_the_class_and_checked(tmp_path):
    classes = ClassStore(tmp_path)
    info = classes.create("4.A", "class")
    child = classes.players(info.id).add("Ana", "cat")
    found = gamemode.find_game("dodge-bees")
    payload = {
        "game": found.to_dict(),
        "source": found.starter,
        "design": {"idea": "Bees!", "win": "Survive", "lose": "A sting"},
    }
    item = classes.share(info.id, child.id, "game", "Bees", payload)
    assert item["kind"] == "game" and item["status"] == "pending"
    for bad in (
        {**payload, "game": {"id": "x"}},
        {**payload, "source": 3},
        {**payload, "design": {"idea": "x" * 400}},
    ):
        with pytest.raises(ClassError):
            classes.share(info.id, child.id, "game", "Bad", bad)


def test_the_game_page_has_the_g1_g2_g3_parts():
    from mse_codezoo import webbuild

    page = (webbuild.WEB_DIR / "game.html").read_text(encoding="utf-8")
    for part in (
        "rounds-box",
        "twists",
        "design-box",
        'id="test"',
        "world-tools",
        "share-link",
        "share-class",
        "together",
        "reactions",
        "class-games",
    ):
        assert part in page, part
    script = (webbuild.WEB_DIR / "game.js").read_text(encoding="utf-8")
    assert "encodeShare" in script and "decodeShare" in script and "roomEvents" in script
    assert "game.html#play=" in (webbuild.WEB_DIR / "classroom.js").read_text(encoding="utf-8")
    assert "t-projector-play" in (webbuild.WEB_DIR / "teacher.html").read_text(encoding="utf-8")


# --- G3: several animals in one world ----------------------------------------------------------


def multi(source=None, names=("Ana", "Ben", "Cy", "Dan"), **extra):
    found = gamemode.find_game("collect-guard") if not extra else spec(**extra)
    game = MultiGame(found, found.starter if source is None else source, [(n, "") for n in names])
    game.start()
    return game


def test_every_animal_gets_its_own_open_start():
    game = multi()
    squares = [tuple(p["at"]) for p in game.state()["players"]]
    assert squares[0] == (4, 4) and len(set(squares)) == 4
    for x, y in squares:
        assert gamemode._walkable(game, x, y)


def test_each_player_moves_its_own_animal():
    game = multi(
        MOVE,
        names=("Ana", "Ben"),
        world={"tiles": [".....", ".....", "....."], "start": [2, 1, "east"]},
    )
    before = {p["number"]: p["at"] for p in game.state()["players"]}
    game.tick_all({1: ["left"], 2: ["down"]})
    after = {p["number"]: p["at"] for p in game.state()["players"]}
    assert after[1] == [before[1][0] - 1, before[1][1]]
    assert after[2] == [before[2][0], before[2][1] + 1]


def test_handlers_know_whose_animal_moves():
    source = (
        "def on_key(key):\n    print(player(), where())\n    go(key)\n"
        "def on_tick():\n    print('all', animals())\n"
    )
    game = multi(
        source,
        names=("Ana", "Ben"),
        world={"tiles": [".....", ".....", "....."], "start": [2, 1, "east"]},
    )
    result = game.tick_all({1: ["up"], 2: ["up"]})
    assert result.output[0].startswith("1 (2, 1)") and result.output[1].startswith("2 ")
    assert result.output[2] == "all [(2, 0), " + result.output[2][13:]


def test_items_and_the_team_score_work_per_animal():
    source = MOVE + "def on_item(item):\n    grab()\n    score.add(1)\n"
    game = multi(
        source,
        names=("Ana", "Ben"),
        world={"tiles": ["B...B", ".....", "....."], "start": [0, 1, "east"]},
    )
    players = game.state()["players"]
    assert players[0]["at"] == [0, 1]
    second = players[1]["at"]
    keys2 = ["up"] if second == [0, 2] else []
    game.tick_all({1: ["up"], 2: keys2})
    assert game.score.value == 1


def test_a_caught_animal_goes_back_to_its_start():
    world = {"tiles": [".....", ".....", "....."], "start": [0, 1, "east"]}
    source = "class Rock(Critter):\n    pass\nRock(1, 1)\n" + MOVE
    game = multi(source, names=("Ana", "Ben"), world=world, rules={"caught": True})
    result = game.tick_all({1: ["right"], 2: []})
    assert game.status == PLAYING
    assert game.state()["players"][0]["at"] == [0, 1] and game.state()["players"][0]["caught"] == 1
    assert any("Ana" in note for note in result.notes)


def test_lose_still_ends_the_game_for_the_team():
    world = {"tiles": [".....", ".....", "....."], "start": [0, 1, "east"]}
    source = (
        "class Rock(Critter):\n    pass\nRock(1, 1)\n"
        + MOVE
        + "def on_touch(c):\n    lose('Oops')\n"
    )
    game = multi(source, names=("Ana", "Ben"), world=world)
    game.tick_all({1: ["right"]})
    assert game.status == LOST and game.message == "Oops"


def test_ten_minutes_of_four_players_replay_without_a_desync():
    """The G3 gate in miniature: 4,000 ticks (10 minutes at 150 ms) of four players
    pressing keys; the recorded inputs give the very same game again."""
    found = gamemode.find_game("chase-frogs")
    source = found.starter.replace(
        "score.add(1)", "score.add(1)\n    build.item(critter.x, critter.y)"
    )
    names = [("Ana", ""), ("Ben", ""), ("Cy", ""), ("Dan", "")]
    game = MultiGame(found, source, names, seed=7)
    game.start()
    rng = random.Random(1)
    sums = []
    for _ in range(4000):
        if game.status != PLAYING:
            break
        game.tick_all(
            {
                n: [rng.choice(["up", "down", "left", "right", "space"])]
                for n in range(1, 5)
                if rng.random() < 0.7
            }
        )
        sums.append(gamerooms.checksum(game.state()))
    again = MultiGame(found, source, names, seed=7)
    again.start()
    for keys, expected in zip(game.multi_inputs, sums, strict=True):
        again.tick_all({int(n): k for n, k in keys.items()})
        assert gamerooms.checksum(again.state()) == expected
    assert replay(found, source, names, game.multi_inputs, seed=7).state() == game.state()


# --- G3: rooms -----------------------------------------------------------------------------------


def test_a_room_fills_starts_and_ticks(rooms):
    room = rooms.open(
        gamemode.find_game("collect-guard"), gamemode.find_game("collect-guard").starter, "Bananas"
    )
    seats = [room.join(f"p{i}", f"Kid {i}", "cat", "") for i in range(4)]
    assert room.join("p0", "Kid 0", "cat", "penguin") is seats[0]  # joining again: the same seat
    with pytest.raises(RoomError, match="full"):
        room.join("p9", "Late", "dog", "")
    with pytest.raises(RoomError, match="opened"):
        room.start(seats[1].token)
    listener = room.listen()
    message = room.start(seats[0].token)
    assert message["type"] == "start" and len(message["state"]["players"]) == 4
    with pytest.raises(RoomError, match="full"):  # running and full: still no fifth animal
        room.join("p8", "New", "dog", "")
    room.keys(seats[1].token, ["up"] * 20)
    assert len(seats[1].keys) == gamemode.MAX_KEYS  # a few keys per request ...
    for _ in range(5):
        room.keys(seats[1].token, ["up"] * 4)
    assert len(seats[1].keys) == gamerooms.MAX_QUEUED  # ... and a few waiting per player
    ticked = room.advance()
    assert (
        ticked["state"]["tick"] == 1
        and len(seats[1].keys) == gamerooms.MAX_QUEUED - gamemode.MAX_KEYS
    )
    room.react(seats[2].token, "🎉")
    with pytest.raises(RoomError):
        room.react(seats[2].token, "hello everyone")  # no chat: only the emoji list
    types = []
    while not listener.empty():
        types.append(listener.get_nowait()["type"])
    assert types == ["room", "room", "start", "tick", "react"]
    room.end("bye")
    assert listener.get_nowait()["type"] == "end" and listener.get_nowait() is None


def test_a_room_checks_seats_and_tidies_up(rooms):
    found = gamemode.find_game("collect-guard")
    room = rooms.open(found, found.starter, "A")
    seat = room.join("p1", "Ana", "cat", "")
    with pytest.raises(RoomError):
        room.keys("not-a-seat", ["up"])
    assert [r["id"] for r in rooms.list()] == [room.id]
    room.leave(seat.token)  # the last one leaves the lobby: the room ends
    assert room.status == gamerooms.ENDED and rooms.list() == []
    with pytest.raises(RoomError):
        rooms.get("nope")


def test_a_paused_class_stops_the_room(rooms):
    found = gamemode.find_game("collect-guard")
    paused = [False]
    rooms.paused = lambda: paused[0]
    room = rooms.open(found, found.starter, "A")
    seat = room.join("p1", "Ana", "cat", "")
    room.start(seat.token)
    paused[0] = True
    assert room.advance() is None
    paused[0] = False
    assert room.advance()["state"]["tick"] == 1


def test_a_room_ticks_by_itself():
    found = gamemode.find_game("collect-guard")
    room = Rooms().open(found, found.starter, "A")
    seat = room.join("p1", "Ana", "cat", "")
    listener = room.listen()
    room.start(seat.token)
    deadline = time.monotonic() + 5
    ticks = 0
    while ticks < 3 and time.monotonic() < deadline:
        message = listener.get(timeout=5)
        if message and message["type"] == "tick":
            ticks += 1
    room.end()
    assert ticks == 3


def test_the_room_api_and_the_offline_build(tmp_path, rooms):
    store = ProfileStore(tmp_path)
    ana = store.add("Ana", "monkey")
    opened = dispatch(
        "POST",
        "/api/room/open",
        {},
        {"game": "collect-guard", "source": MOVE, "profile": ana.id, "look": "penguin"},
        store,
    )
    assert opened["number"] == 1 and opened["room"]["players"][0]["name"] == "Ana"
    assert opened["game"]["id"] == "collect-guard"
    guest = dispatch("POST", "/api/room/join", {}, {"room": opened["room"]["id"]}, store)
    assert guest["number"] == 2 and guest["room"]["players"][1]["name"] == "Guest"
    with pytest.raises(ApiError):
        dispatch(
            "POST",
            "/api/room/start",
            {},
            {"room": opened["room"]["id"], "seat": guest["seat"]},
            store,
        )
    started_ = dispatch(
        "POST", "/api/room/start", {}, {"room": opened["room"]["id"], "seat": opened["seat"]}, store
    )
    assert started_["state"]["status"] == PLAYING
    listed = dispatch("GET", "/api/rooms", {}, {}, store)
    assert listed["rooms"][0]["status"] == "playing" and "🎉" in listed["reactions"]
    stream = dispatch("GET", "/api/room/events", {"room": opened["room"]["id"]}, {}, store)
    assert isinstance(stream, gamerooms.EventStream)
    answer = json.loads(dispatch_json("GET", "/api/rooms", "{}", "{}", store, "en"))
    assert answer["status"] == 404 and "hub" in answer["data"]["error"]


# --- G3: over the classroom hub -------------------------------------------------------------------


@pytest.fixture
def hub_server(tmp_path, monkeypatch):
    monkeypatch.setattr(gamerooms, "ROOMS", Rooms())
    store = ClassStore(tmp_path)
    info = store.create("Game club", "workshop")
    ana = store.players(info.id).add("Ana", "cat")
    ben = store.players(info.id).add("Ben", "dog")
    hub = Hub(store, info.id)
    server = CodeZooServer("127.0.0.1", 0, hub=hub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", hub, ana.id, ben.id
    gamerooms.ROOMS.close_all()
    server.shutdown()
    server.server_close()


def call(base, path, body=None, *, code=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if code:
        req.add_header("X-Class-Code", code)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_two_children_play_one_world_over_the_hub(hub_server):
    base, hub, ana, ben = hub_server
    code = hub.code
    status, _ = call(
        base, "/api/room/open", {"game": "collect-guard", "source": MOVE, "profile": ana}
    )
    assert status == 403  # no class code
    status, _ = call(
        base,
        "/api/room/open",
        {"game": "collect-guard", "source": MOVE, "profile": "p00000000"},
        code=code,
    )
    assert status == 403  # not one of the class's players
    status, opened = call(
        base, "/api/room/open", {"game": "collect-guard", "source": MOVE, "profile": ana}, code=code
    )
    assert status == 200
    room = opened["room"]["id"]
    status, joined = call(base, "/api/room/join", {"room": room, "profile": ben}, code=code)
    assert joined["number"] == 2
    # the event stream takes the class code in the address (an EventSource has no headers)
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"{base}/api/room/events?room={room}", timeout=5)
    stream = urllib.request.urlopen(f"{base}/api/room/events?room={room}&code={code}", timeout=10)
    assert stream.headers["Content-Type"].startswith("text/event-stream")
    first = json.loads(stream.readline().decode().removeprefix("data: "))
    assert first["type"] == "room" and len(first["room"]["players"]) == 2
    call(base, "/api/room/start", {"room": room, "seat": opened["seat"]}, code=code)
    call(
        base, "/api/room/keys", {"room": room, "seat": joined["seat"], "keys": ["left"]}, code=code
    )
    seen = []
    while len([m for m in seen if m["type"] == "tick"]) < 3:
        line = stream.readline().decode().strip()
        if line.startswith("data: "):
            seen.append(json.loads(line.removeprefix("data: ")))
    ticks = [m for m in seen if m["type"] == "tick"]
    assert all(len(m["state"]["players"]) == 2 for m in ticks)
    assert [m["state"]["tick"] for m in ticks] == sorted(m["state"]["tick"] for m in ticks)
    stream.close()
    # the teacher's pause stops the world; ending the class closes it
    hub.paused = True
    status, _ = call(
        base, "/api/room/keys", {"room": room, "seat": joined["seat"], "keys": ["up"]}, code=code
    )
    assert status == 423
    hub.paused = False
    hub.end()
    assert gamerooms.ROOMS.list() == []


# --- after G3: doors, switches, power-ups, sounds, "which handler fired", 3D together ------

THINGS_WORLD = {
    "tiles": [".....", ".....", "....."],
    "start": [0, 0, "east"],
    "objects": [
        {"at": [2, 0], "type": "door", "name": "gate"},
        {"at": [0, 2], "type": "switch", "door": "gate"},
        {"at": [1, 1], "type": "power"},
    ],
}


def test_a_closed_door_blocks_and_a_switch_opens_it():
    source = MOVE + "def on_switch(name):\n    print('switch', name, door(name).is_open())\n"
    game = started(source, world=THINGS_WORLD)
    assert game.state()["doors"] == [[2, 0, False]]
    assert [2, 0] not in game.state()["walls"]  # drawn as a door, not a stone
    game.tick(["right"])
    game.tick(["right"])  # bumps into the closed door
    assert game.world.x == 1
    game.tick(["left"])
    game.tick(["down"])
    result = game.tick(["down"])  # onto the switch
    assert game.state()["doors"] == [[2, 0, True]] and game.state()["switches"] == [[0, 2, True]]
    assert result.output == ["switch gate True"]
    assert {"type": "door", "at": [2, 0], "open": True} in result.events


def test_programs_open_and_close_doors():
    source = "door('gate').open()\nprint(door('gate').is_open())\ndoor('gate').toggle()\n"
    game = started(source, world=THINGS_WORLD)
    assert game.output == ["True"] and game.state()["doors"] == [[2, 0, False]]
    assert started("door('nope')\n", world=THINGS_WORLD).status == BROKEN
    # a door never closes on someone
    open_world = THINGS_WORLD | {
        "start": [2, 0, "east"],
        "objects": [{"at": [3, 0], "type": "door", "open": True}],
    }
    game = Game(spec(world=open_world), MOVE + "def on_tick():\n    door().close()\n")
    game.start()
    result = game.tick(["right"])
    assert game.state()["doors"] == [[3, 0, True]] and any("can't close" in n for n in result.notes)


def test_a_power_up_freezes_critters_or_calls_on_power():
    critter = (
        "class G(Critter):\n    def on_tick(self):\n"
        "        self.turn_around()\n        self.step()\nG(4, 2)\n"
    )
    game = started(critter + MOVE, world=THINGS_WORLD)
    game.tick(["down"])
    result = game.tick(["right"])  # onto the power-up
    assert game.state()["powers"] == [] and game.state()["frozen"] == gamemode.FREEZE_TICKS
    at = game.state()["critters"][0]["at"]
    game.tick([])
    assert game.state()["critters"][0]["at"] == at  # frozen
    assert any("freeze" in note for note in result.notes)
    custom = started(critter + MOVE + "def on_power():\n    score.add(5)\n", world=THINGS_WORLD)
    custom.tick(["down"])
    custom.tick(["right"])
    assert custom.score.value == 5 and custom.state()["frozen"] == 0


def test_bad_door_and_switch_objects_are_refused():
    with pytest.raises(GameError, match="type"):
        spec(world=WORLD | {"objects": [{"at": [0, 1], "type": "trampoline"}]})
    with pytest.raises(GameError, match="name"):
        spec(world=WORLD | {"objects": [{"at": [0, 1], "type": "door", "name": "my door"}]})
    with pytest.raises(GameError, match="open"):
        spec(world=WORLD | {"objects": [{"at": [0, 1], "type": "door", "open": "yes"}]})


def test_the_bot_counts_doors_as_passable_and_tries_switches():
    world = {
        "tiles": ["..#B", "..#.", "...."],
        "start": [0, 0, "east"],
        "objects": [{"at": [2, 2], "type": "door"}, {"at": [0, 2], "type": "switch"}],
    }
    report = gamemode.playtest(
        spec(world=world, rules={"win": "collect_all"}),
        MOVE + "def on_item(item):\n    grab()\n",
        games=3,
    )
    assert report["unreachable"] == [] and report["won"] >= 1


def test_sound_plays_a_few_known_sounds_per_tick():
    game = started("def on_tick():\n    for i in range(10):\n        sound('ding')\n")
    result = game.tick([])
    assert [e for e in result.events if e["type"] == "sound"] == [
        {"type": "sound", "name": "ding"}
    ] * gamemode.MAX_SOUNDS
    assert started("sound('siren')\n").status == BROKEN


def test_every_tick_says_which_handler_fired_and_what_it_changed():
    source = (
        "class G(Critter):\n    def on_tick(self):\n        self.turn_left()\n"
        "G(4, 2)\nG(0, 2)\n"
        + MOVE
        + "def on_tick():\n    if ticks() == 2:\n        score.add(1)\n        print('two')\n"
    )
    game = started(source)
    first = game.tick(["left"])
    assert first.fired == [
        {"handler": "on_key", "times": 1, "steps": first.fired[0]["steps"], "changes": ["animal"]},
        {"handler": "on_tick", "times": 1, "steps": first.fired[1]["steps"], "changes": []},
        {
            "handler": "G.on_tick",
            "times": 2,
            "steps": first.fired[2]["steps"],
            "changes": ["critters"],
        },
    ]
    second = game.to_json(game.tick([]))
    on_tick = next(f for f in second["fired"] if f["handler"] == "on_tick")
    assert on_tick["changes"] == ["printed", "score"]


def test_the_maze_template_has_a_door_a_switch_and_a_power_up():
    found = gamemode.find_game("maze-ghost")
    types = sorted(o.get("type", "") for o in found.objects())
    assert types == ["door", "power", "switch"]


def test_playing_together_works_on_the_3d_stage_too():
    from mse_codezoo import webbuild

    stage = (webbuild.WEB_DIR / "stage3d.js").read_text(encoding="utf-8")
    for part in (
        "showPlayers(players",
        "makeDoor()",
        "makeSwitch()",
        "makePower()",
        "makePlayerRing(number)",
    ):
        assert part in stage, part
    script = (webbuild.WEB_DIR / "game.js").read_text(encoding="utf-8")
    assert "state.stage3d.squareAt(event)" in script  # the world is edited on the 3D stage too
    assert "playSounds(" in script and "drawLanes()" in script
    fun = (webbuild.WEB_DIR / "fun.js").read_text(encoding="utf-8")
    for name in gamemode.SOUNDS:
        assert f"  {name}(" in fun, name  # every sound a program can ask for exists


def test_a_child_can_join_a_game_that_has_started(rooms):
    spec = gamemode.find_game("collect-guard")
    room = rooms.open(spec, spec.starter, "Bananas")
    first = room.join("p1", "Ema", "cat", "")
    room.start(first.token)
    assert room.public()["joinable"] is True
    for _ in range(3):
        room.keys(first.token, ["right"])
        room.advance()
    late = room.join("p2", "Ben", "dog", "penguin")  # the game is running
    assert room.number(late) == 2
    players = room.game.state()["players"]
    assert [p["name"] for p in players] == ["Ema", "Ben"]
    assert players[0]["at"] != players[1]["at"]  # a square of its own, near the start
    for _ in range(4):
        room.keys(late.token, ["down"])
        room.keys(first.token, ["right"])
        room.advance()
    # lockstep: the replay adds Ben before the same tick and ends in the same world
    game = room.game
    again = gamerooms.replay(spec, spec.starter, [("Ema", "")], game.multi_inputs, joins=game.joins)
    assert gamerooms.checksum(again.state()) == gamerooms.checksum(game.state())
    assert game.joins == [{"tick": 3, "name": "Ben", "look": "penguin"}]


def test_the_teacher_sees_and_closes_game_worlds(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("3.B", "workshop").id)
    head = {"X-Teacher-Token": hub.teacher_token}
    spec = gamemode.find_game("collect-guard")
    room = gamerooms.ROOMS.open(spec, spec.starter, "Bananas")
    try:
        seat = room.join("p1", "Ema", "cat", "")
        overview = hub.handle("GET", "/api/teacher/overview", {}, {}, head, "t")
        shown = [r for r in overview["rooms"] if r["id"] == room.id]
        assert shown and shown[0]["players"][0]["name"] == "Ema" and shown[0]["tick"] == 0
        assert {"score", "minutes", "status", "title"} <= set(shown[0])
        after = hub.handle("POST", "/api/teacher/room/close", {}, {"room": room.id}, head, "t")
        assert room.id not in [r["id"] for r in after["rooms"]] and room.status == "ended"
        with pytest.raises(RoomError):
            room.keys(seat.token, ["up"]) or gamerooms.ROOMS.get(room.id)
    finally:
        gamerooms.ROOMS.close_all()


def test_the_score_bug_hunt():
    """Two handlers fight over the score: the lesson starts broken, round 1 fixes it."""
    found = gamemode.find_game("bug-score")
    broken = Game(found, found.lesson)
    broken.start()
    broken.tick(["up"])  # onto the banana: on_item adds a point (on_tick ran before it)...
    assert broken.score.value == 1
    after = broken.to_json(broken.tick([]))  # ...and on the next tick on_tick takes it away
    assert broken.score.value == 0
    # "Which handler fired?" shows the thief: on_tick changed the score
    assert "on_tick" in {entry["handler"] for entry in after["fired"]}
    first = found.rounds[0]
    assert not gamemode.round_done(first["needs"], broken.features())
    fixed_source = found.lesson.replace("    score.set(0)\n", "    pass\n")
    fixed = Game(found, fixed_source)
    fixed.start()
    fixed.tick(["up"])
    assert fixed.score.value == 1
    assert gamemode.round_done(first["needs"], fixed.features())
