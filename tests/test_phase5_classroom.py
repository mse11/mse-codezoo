"""Phase 5: the classroom hub. Classes and workshops, the class code, the teacher's screen,
today's levels, the pause, the class's own levels, sharing, export and ending a class.

The hub is tested over real HTTP on localhost, like ``test_server.py``.
"""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from mse_codezoo.classes import ClassError, ClassStore, normalize_code
from mse_codezoo.cli import main
from mse_codezoo.hub import Hub, local_address
from mse_codezoo.profiles import CLASS_PICTURES, PICTURES, ProfileError, ProfileStore
from mse_codezoo.server import CodeZooServer

LEVELS = Path(__file__).parents[1] / "mse_codezoo" / "content" / "levels"
SOLUTION = (LEVELS / "m01-sequences" / "l01.solution.py").read_text(encoding="utf-8")


def own_level(level_id="our-first"):
    data = json.loads((LEVELS / "m01-sequences" / "l01.json").read_text(encoding="utf-8"))
    data["id"] = level_id
    data["title"] = "Our first level"
    return data


# --- the class store ----------------------------------------------------------------------


def test_class_types_set_the_defaults(tmp_path):
    store = ClassStore(tmp_path)
    workshop = store.create("Saturday club", "workshop")
    regular = store.create("3.B", "class")
    assert workshop.settings == {
        "roster": False, "names": True, "deleteAtEnd": True, "cub": False, "assigned": [],
        "locked": True,
    }  # fmt: skip
    assert regular.settings["roster"] and regular.settings["names"]
    assert not regular.settings["deleteAtEnd"]
    custom = store.create("Mixed", "workshop", names=True)
    assert custom.settings["names"] and custom.settings["deleteAtEnd"]
    assert sorted(c.name for c in store.classes()) == ["3.B", "Mixed", "Saturday club"]


def test_class_names_are_checked(tmp_path):
    store = ClassStore(tmp_path)
    store.create("3.B", "class")
    with pytest.raises(ClassError):
        store.create("3.b", "class")  # the same name in another letter case
    with pytest.raises(ClassError):
        store.create("Chess", "lesson")
    with pytest.raises(ClassError):
        store.create("   ")
    with pytest.raises(ClassError):
        store.find("../../etc")


def test_a_class_has_32_pictures_and_a_family_keeps_eight(tmp_path):
    assert len(CLASS_PICTURES) == 32 == len(set(CLASS_PICTURES))
    assert CLASS_PICTURES[: len(PICTURES)] == PICTURES
    store = ClassStore(tmp_path)
    players = store.players(store.create("3.B", "class").id)
    assert players.add("Ema", "hedgehog").picture == "hedgehog"
    with pytest.raises(ProfileError):
        ProfileStore(tmp_path / "home").add("Ema", "hedgehog")


def test_a_class_player_goes_home_with_their_picture(tmp_path):
    store = ClassStore(tmp_path)
    players = store.players(store.create("3.B", "class").id)
    profile = players.add("Ema", "unicorn")
    home = ProfileStore(tmp_path / "home")
    imported = home.import_(players.export(profile.id))
    assert (imported.name, imported.picture) == ("Ema", "unicorn")


def test_class_codes_are_easy_to_type():
    assert normalize_code(" mango 427 ") == "MANGO-427"
    assert normalize_code("Mango-427") == "MANGO-427"


def test_teacher_levels_are_checked_first(tmp_path):
    store = ClassStore(tmp_path)
    info = store.create("3.B", "class")
    assert store.add_level(info.id, own_level(), SOLUTION) == []
    assert list(store.levels(info.id)) == ["our-first"]
    assert store.add_level(info.id, own_level("m01-l01"), SOLUTION)  # a built-in id
    assert store.add_level(info.id, own_level("bad id!"), SOLUTION)
    assert store.add_level(info.id, own_level("x"), "step()\n")  # doesn't solve it
    assert store.add_level(info.id, {"id": "x"}, SOLUTION)  # not a level
    store.update(info.id, assigned=["our-first"])
    store.remove_level(info.id, "our-first")
    assert store.levels(info.id) == {}
    assert store.find(info.id).settings["assigned"] == []


# --- the hub over HTTP ------------------------------------------------------------------


@pytest.fixture
def hub_server(tmp_path):
    store = ClassStore(tmp_path)
    info = store.create("Saturday club", "workshop")
    hub = Hub(store, info.id, base_url="http://192.168.1.20:8765/")
    server = CodeZooServer("127.0.0.1", 0, hub=hub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", hub, store
    server.shutdown()
    server.server_close()


def call(base, path, body=None, *, code=None, key=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if code:
        req.add_header("X-Class-Code", code)
    if key:
        req.add_header("X-Teacher-Token", key)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_the_class_code_is_needed(hub_server):
    base, hub, _ = hub_server
    status, info = call(base, "/api/info")
    assert status == 200 and info["hub"] == {
        "name": "Saturday club",
        "type": "workshop",
        "lang": None,
    }
    assert call(base, "/api/levels")[0] == 403
    assert call(base, "/api/levels", code="WRONG-1")[0] == 403
    status, levels = call(base, "/api/levels", code=hub.code.lower())
    assert status == 200 and [lv for lv in levels if not lv["cub"]][0]["id"] == "m01-l01"
    status, page = 0, b""
    with urllib.request.urlopen(base + "/teacher.html", timeout=10) as response:
        status, page = response.status, response.read()
    assert status == 200 and b"teacher.js" in page  # pages themselves are open


def test_joining_and_wrong_codes(hub_server):
    base, hub, _ = hub_server
    status, joined = call(base, "/api/class/join", {"code": hub.code.replace("-", " ")})
    assert status == 200
    assert joined["code"] == hub.code
    assert joined["class"]["roster"] is False and len(joined["pictures"]) == 32
    for _ in range(10):
        assert call(base, "/api/class/join", {"code": "NOPE-100"})[0] == 403
    status, answer = call(base, "/api/class/join", {"code": hub.code})
    assert status == 429  # even the right code waits now
    assert "Wait" in answer["error"]


def test_children_may_share_a_picture_and_names_tell_them_apart(hub_server):
    base, hub, _ = hub_server
    key = hub.teacher_token
    status, ema = call(base, "/api/class/me", {"picture": "cat", "name": " Ema "}, code=hub.code)
    assert status == 200 and ema["picture"] == "cat" and ema["name"] == "Ema"
    status, again = call(base, "/api/class/me", {"picture": "dog", "name": "ema"}, code=hub.code)
    assert status == 400 and "already a player" in again["error"]  # a typed name is taken
    _, cat = call(base, "/api/class/me", {"picture": "cat"}, code=hub.code)
    _, cat2 = call(base, "/api/class/me", {"picture": "cat", "name": ""}, code=hub.code)
    assert (cat["picture"], cat["name"]) == ("cat", "cat")
    assert (cat2["picture"], cat2["name"]) == ("cat", "cat 2")  # no name: numbered
    call(base, "/api/teacher/settings", {"names": False}, key=key)
    _, cat3 = call(base, "/api/class/me", {"picture": "cat", "name": "Leo"}, code=hub.code)
    assert cat3["name"] == "cat 3"  # names off: the typed name is ignored
    status, joined = call(base, "/api/class/join", {"code": hub.code})
    assert [p["picture"] for p in joined["players"]].count("cat") == 4


def test_a_roster_class_only_lets_the_teacher_add_players(hub_server):
    base, hub, _ = hub_server
    key = hub.teacher_token
    call(base, "/api/teacher/settings", {"roster": True, "names": True}, key=key)
    assert call(base, "/api/class/me", {"picture": "cat"}, code=hub.code)[0] == 403
    status, ema = call(base, "/api/teacher/player", {"name": "Ema", "picture": "owl"}, key=key)
    assert status == 200
    status, joined = call(base, "/api/class/join", {"code": hub.code})
    assert joined["class"]["roster"] and [p["name"] for p in joined["players"]] == ["Ema"]
    status, renamed = call(
        base, "/api/teacher/player/rename", {"profile": ema["id"], "name": "Emka"}, key=key
    )
    assert renamed["name"] == "Emka"


def test_grown_up_routes_are_closed_in_a_class(hub_server):
    base, hub, _ = hub_server
    assert call(base, "/api/parent/check", {}, code=hub.code)[0] == 403
    assert call(base, "/api/profiles", code=hub.code)[0] == 403  # everyone's stars
    assert call(base, "/api/profiles", {"name": "X", "picture": "cat"}, code=hub.code)[0] == 403


def test_level_ids_cannot_reach_files(hub_server):
    base, hub, _ = hub_server
    path = "/api/levels/..%2F..%2Fpyproject.json"
    assert call(base, path, code=hub.code)[0] == 404


def test_teacher_routes_need_the_teacher_key(hub_server):
    base, hub, _ = hub_server
    assert call(base, "/api/teacher/overview")[0] == 403
    assert (
        call(base, "/api/teacher/overview", code=hub.code)[0] == 403
    )  # the class code isn't enough
    status, overview = call(base, "/api/teacher/overview", key=hub.teacher_token)
    assert status == 200
    assert overview["code"] == hub.code
    assert overview["joinUrl"] == f"http://192.168.1.20:8765/?class={hub.code}"
    assert overview["qr"].startswith("<svg")
    # the teacher's key also opens the game routes (the editor on the teacher's computer)
    assert call(base, "/api/levels", key=hub.teacher_token)[0] == 200


def test_runs_count_for_the_class_player_and_the_teacher_sees_who_is_stuck(hub_server):
    base, hub, _ = hub_server
    _, me = call(base, "/api/class/me", {"picture": "fox"}, code=hub.code)
    run = {"level": "m01-l01", "source": SOLUTION, "profile": me["id"]}
    status, result = call(base, "/api/run", run, code=hub.code)
    assert status == 200 and result["progress"]["solved"]
    for _ in range(3):
        call(base, "/api/run", {**run, "level": "m01-l02", "source": "step()\n"}, code=hub.code)
    _, overview = call(base, "/api/teacher/overview", key=hub.teacher_token)
    player = overview["players"][0]
    assert player["stars"] == 3 and player["solved"] == 1
    assert player["modules"]["sequences"]["solved"] == 1
    assert [s["level"] for s in player["stuck"]] == ["m01-l02"]
    stats = {row["level"]: (row["tried"], row["solved"]) for row in overview["levelStats"]}
    assert stats == {"m01-l01": (1, 1), "m01-l02": (1, 0)}
    assert overview["concepts"] and overview["mistakes"]


def test_todays_levels_and_the_pause(hub_server):
    base, hub, _ = hub_server
    key = hub.teacher_token
    assigned = ["m01-l03", "m01-l02"]
    _, levels = call(base, "/api/levels", code=hub.code)
    assert len(levels) > 2  # nothing saved yet: every level
    call(base, "/api/teacher/settings", {"assigned": assigned}, key=key)
    _, levels = call(base, "/api/levels", code=hub.code)
    assert [lv["id"] for lv in levels] == assigned  # saved picks only, in the teacher's order
    call(base, "/api/teacher/settings", {"locked": False}, key=key)
    _, levels = call(base, "/api/levels", code=hub.code)
    assert len(levels) > 2 and {lv["id"] for lv in levels if lv["assigned"]} == set(assigned)
    call(base, "/api/teacher/settings", {"locked": True}, key=key)
    status, _ = call(base, "/api/run", {"level": "m01-l01", "source": SOLUTION}, code=hub.code)
    assert status == 403
    assert call(base, "/api/run", {"level": "m01-l02", "source": "step()"}, code=hub.code)[0] == 200
    call(base, "/api/teacher/pause", {"paused": True}, key=key)
    _, state = call(base, "/api/class/state", code=hub.code)
    assert state["paused"] and state["locked"] and state["assigned"] == assigned
    status, answer = call(base, "/api/run", {"level": "m01-l02", "source": "step()"}, code=hub.code)
    assert status == 423 and "teacher" in answer["error"]
    call(base, "/api/teacher/pause", {"paused": False}, key=key)
    assert call(base, "/api/run", {"level": "m01-l02", "source": "step()"}, code=hub.code)[0] == 200


def test_the_class_plays_its_own_levels(hub_server):
    base, hub, _ = hub_server
    key = hub.teacher_token
    status, answer = call(
        base, "/api/teacher/level", {"level": own_level(), "solution": SOLUTION}, key=key
    )
    assert status == 200 and answer == {"ok": True, "errors": []}
    status, answer = call(
        base, "/api/teacher/level", {"level": own_level("x"), "solution": "pass"}, key=key
    )
    assert not answer["ok"] and answer["errors"]
    _, levels = call(base, "/api/levels", code=hub.code)
    assert levels[-1]["id"] == "our-first" and levels[-1]["own"]
    status, level = call(base, "/api/levels/our-first", code=hub.code)
    assert status == 200 and level["title"] == "Our first level"
    _, me = call(base, "/api/class/me", {"picture": "bee"}, code=hub.code)
    run = {"level": "our-first", "source": SOLUTION, "profile": me["id"]}
    status, result = call(base, "/api/run", run, code=hub.code)
    assert status == 200 and result["progress"]["solved"]
    _, overview = call(base, "/api/teacher/overview", key=key)
    mine = next(m for m in overview["modules"] if m["id"] == "mine")
    assert mine["levels"] == [{"id": "our-first", "title": "Our first level"}]


def test_shares_wait_for_the_teacher(hub_server):
    base, hub, _ = hub_server
    key = hub.teacher_token
    _, me = call(base, "/api/class/me", {"picture": "crab"}, code=hub.code)
    payload = {"level": "m01-l01", "source": SOLUTION, "animal": "monkey"}
    body = {"profile": me["id"], "kind": "program", "title": "My walk", "payload": payload}
    status, share = call(base, "/api/class/share", body, code=hub.code)
    assert status == 200 and share["status"] == "pending"
    assert call(base, "/api/class/shares", code=hub.code)[1] == {"shares": []}
    call(base, "/api/teacher/share", {"share": share["id"], "status": "approved"}, key=key)
    _, shares = call(base, "/api/class/shares", code=hub.code)
    assert [s["title"] for s in shares["shares"]] == ["My walk"]
    assert call(base, "/api/class/state", code=hub.code)[1]["shares"] == 1
    assert call(base, "/api/class/report", {"share": share["id"]}, code=hub.code)[0] == 200
    assert call(base, "/api/class/shares", code=hub.code)[1] == {"shares": []}
    _, overview = call(base, "/api/teacher/overview", key=key)
    assert overview["shares"][0]["status"] == "reported"
    too_big = {**body, "payload": {"level": "m01-l01", "source": "x" * 300_000}}
    assert call(base, "/api/class/share", too_big, code=hub.code)[0] in (400, 413)
    odd = {**body, "kind": "photo"}
    assert call(base, "/api/class/share", odd, code=hub.code)[0] == 400
    call(base, "/api/teacher/share", {"share": share["id"], "status": "deleted"}, key=key)
    assert call(base, "/api/teacher/overview", key=key)[1]["shares"] == []


def test_progress_goes_home_and_comes_back(hub_server, tmp_path):
    base, hub, _ = hub_server
    _, me = call(base, "/api/class/me", {"picture": "panda"}, code=hub.code)
    call(
        base,
        "/api/run",
        {"level": "m01-l01", "source": SOLUTION, "profile": me["id"]},
        code=hub.code,
    )
    status, file = call(base, "/api/class/export", {"profile": me["id"]}, code=hub.code)
    assert status == 200 and file["format"] == "codezoo-profile"
    home = ProfileStore(tmp_path / "home")
    player = home.import_(file)
    assert home.progress(player.id)["levels"]["m01-l01"]["solved"]
    # and back to class: the picture is taken, so the child gets a free one
    status, again = call(base, "/api/class/import", {"data": home.export(player.id)}, code=hub.code)
    assert status == 200 and again["picture"] == "panda" and again["name"] == "panda 2"


def test_the_whole_class_in_one_file(hub_server):
    base, hub, _ = hub_server
    call(base, "/api/class/me", {"picture": "frog"}, code=hub.code)
    call(base, "/api/class/me", {"picture": "lion"}, code=hub.code)
    status, file = call(base, "/api/teacher/export", {}, key=hub.teacher_token)
    assert status == 200 and file["format"] == "codezoo-class-export"
    assert sorted(p["profile"]["picture"] for p in file["players"]) == ["frog", "lion"]
    assert all(p["format"] == "codezoo-profile" for p in file["players"])


def test_ending_a_class_keeps_its_players_and_changes_the_code(tmp_path):
    store = ClassStore(tmp_path)
    info = store.create("3.B", "class")
    store.players(info.id).add("Ema", "owl")
    hub = Hub(store, info.id)
    old = hub.code
    answer = hub.end()
    assert answer["deleted"] is False and hub.code != old
    assert [p.name for p in store.players(info.id).profiles()] == ["Ema"]


def test_ending_a_workshop_deletes_its_data(hub_server):
    base, hub, store = hub_server
    call(base, "/api/class/me", {"picture": "frog"}, code=hub.code)
    status, answer = call(base, "/api/teacher/end", {}, key=hub.teacher_token)
    assert status == 200 and answer["deleted"]
    assert store.classes() == []
    assert call(base, "/api/levels", code=hub.code)[0] == 410
    assert call(base, "/api/class/join", {"code": hub.code})[0] == 410
    assert "hub" not in call(base, "/api/info")[1]


def test_a_new_code_locks_out_the_old_one(hub_server):
    base, hub, _ = hub_server
    old = hub.code
    status, answer = call(base, "/api/teacher/code", {}, key=hub.teacher_token)
    assert status == 200 and answer["code"] != old
    assert call(base, "/api/levels", code=old)[0] == 403
    assert call(base, "/api/levels", code=answer["code"])[0] == 200


def test_the_local_address_is_text():
    assert local_address().count(".") == 3


# --- at home ------------------------------------------------------------------------------


def test_grown_ups_can_load_a_player_from_a_file(tmp_path):
    from mse_codezoo.server import dispatch

    school = ProfileStore(tmp_path / "school")
    ema = school.add("Ema", "fox")
    home = ProfileStore(tmp_path / "home")
    data = dispatch("POST", "/api/parent/import", {}, {"data": school.export(ema.id)}, home)
    assert data["name"] == "Ema" and [p.name for p in home.profiles()] == ["Ema"]
    with pytest.raises(ProfileError):
        dispatch("POST", "/api/parent/import", {}, {"data": "nope"}, home)


# --- the command line ---------------------------------------------------------------------


def test_class_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEZOO_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["class", "new", "3.B", "--type", "class"])
    assert result.exit_code == 0, result.output
    assert "the teacher adds players" in result.output
    result = runner.invoke(main, ["class", "add-player", "3.B", "Ema", "--picture", "owl"])
    assert result.exit_code == 0, result.output
    level_file = tmp_path / "our-first.json"
    level_file.write_text(json.dumps(own_level()), encoding="utf-8")
    (tmp_path / "our-first.solution.py").write_text(SOLUTION, encoding="utf-8")
    result = runner.invoke(main, ["class", "add-level", "3.B", str(level_file)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(main, ["class", "list"])
    assert "3.B" in result.output and "1 player(s)" in result.output
    out = tmp_path / "class.json"
    result = runner.invoke(main, ["class", "export", "3.B", "-o", str(out)])
    assert (
        result.exit_code == 0
        and json.loads(out.read_text())["players"][0]["profile"]["name"] == "Ema"
    )
    result = runner.invoke(main, ["class", "delete", "3.B", "--yes"])
    assert result.exit_code == 0 and ClassStore(tmp_path).classes() == []
    result = runner.invoke(main, ["class", "delete", "3.B", "--yes"])
    assert result.exit_code != 0 and "No class" in result.output


def test_the_class_language_goes_into_the_join_link(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("2.A", "class", lang="sk").id, base_url="http://h/")
    assert hub.join_url == f"http://h/?class={hub.code}&lang=sk"
    head = {"X-Teacher-Token": hub.teacher_token}
    info = hub.handle("GET", "/api/info", {}, {}, {}, "c")
    assert info["hub"]["lang"] == "sk"
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"lang": ""}, head, "t")
    assert overview["class"]["lang"] is None and overview["joinUrl"].endswith(hub.code)
    with pytest.raises(ClassError):
        hub.handle("POST", "/api/teacher/settings", {}, {"lang": "de"}, head, "t")
    with pytest.raises(ClassError):
        classes.create("3.A", "class", lang="xx")


def test_a_served_class_waits_until_the_teacher_starts_the_lesson(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("1.B", "workshop").id, start_paused=True)
    code, head = {"X-Class-Code": hub.code}, {"X-Teacher-Token": hub.teacher_token}
    state = hub.handle("GET", "/api/class/state", {}, {}, code, "c")
    assert state["paused"] and state["started"] is False
    body = {"level": "m01-l01", "source": "step(4)\ngrab()\n"}
    with pytest.raises(Exception) as caught:
        hub.handle("POST", "/api/run", {}, body, code, "c")
    assert "getting the lesson ready" in str(caught.value)
    assert not hub.handle("GET", "/api/teacher/overview", {}, {}, head, "t")["started"]
    hub.handle("POST", "/api/teacher/pause", {}, {"paused": False}, head, "t")
    assert hub.handle("POST", "/api/run", {}, body, code, "c")["check"]["solved"]
    hub.handle("POST", "/api/teacher/pause", {}, {"paused": True}, head, "t")
    state = hub.handle("GET", "/api/class/state", {}, {}, code, "c")
    assert state["paused"] and state["started"]  # a pause now, not "getting ready"


def test_the_teacher_picks_the_stage_views(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("4.C", "class").id)
    code, head = {"X-Class-Code": hub.code}, {"X-Teacher-Token": hub.teacher_token}
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["views"] == ["2d", "3d"]
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"views": ["2d"]}, head, "t")
    assert overview["class"]["views"] == ["2d"]
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["views"] == ["2d"]
    for wrong in ([], ["4d"], "2d"):
        with pytest.raises(ClassError):
            hub.handle("POST", "/api/teacher/settings", {}, {"views": wrong}, head, "t")


def test_the_teacher_picks_the_sounds(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("4.D", "workshop").id)
    code, head = {"X-Class-Code": hub.code}, {"X-Teacher-Token": hub.teacher_token}
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["sounds"] == ["on", "off"]
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"sounds": ["off"]}, head, "t")
    assert overview["class"]["sounds"] == ["off"]
    assert overview["class"]["views"] == ["2d", "3d"]  # the stage is left alone
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["sounds"] == ["off"]
    for wrong in ([], ["loud"], "off"):
        with pytest.raises(ClassError):
            hub.handle("POST", "/api/teacher/settings", {}, {"sounds": wrong}, head, "t")


def test_the_teacher_picks_the_colours(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("4.E", "workshop").id)
    code, head = {"X-Class-Code": hub.code}, {"X-Teacher-Token": hub.teacher_token}
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["themes"] == ["light", "dark"]
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"themes": ["dark"]}, head, "t")
    assert overview["class"]["themes"] == ["dark"]
    assert overview["class"]["sounds"] == ["on", "off"]  # the sounds are left alone
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["themes"] == ["dark"]
    for wrong in ([], ["purple"], "dark"):
        with pytest.raises(ClassError):
            hub.handle("POST", "/api/teacher/settings", {}, {"themes": wrong}, head, "t")


def test_the_teacher_picks_the_panes(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("1.A", "workshop").id)
    code, head = {"X-Class-Code": hub.code}, {"X-Teacher-Token": hub.teacher_token}
    everything = ["blocks", "code", "console"]
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["panes"] == everything
    # small children: only the blocks
    overview = hub.handle("POST", "/api/teacher/settings", {}, {"panes": ["blocks"]}, head, "t")
    assert overview["class"]["panes"] == ["blocks"]
    assert overview["class"]["themes"] == ["light", "dark"]  # the colours are left alone
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["panes"] == ["blocks"]
    # kept in the pane order whatever order they come in
    hub.handle("POST", "/api/teacher/settings", {}, {"panes": ["console", "blocks"]}, head, "t")
    assert hub.handle("GET", "/api/class/state", {}, {}, code, "c")["panes"] == [
        "blocks",
        "console",
    ]
    for wrong in ([], ["stage"], "blocks"):
        with pytest.raises(ClassError):
            hub.handle("POST", "/api/teacher/settings", {}, {"panes": wrong}, head, "t")


def test_a_child_can_have_their_own_stage_and_language(tmp_path):
    from mse_codezoo.hub import Hub

    classes = ClassStore(tmp_path)
    hub = Hub(classes, classes.create("5.D", "class", lang="sk").id)
    code, head = {"X-Class-Code": hub.code}, {"X-Teacher-Token": hub.teacher_token}
    hub.handle("POST", "/api/teacher/settings", {}, {"views": ["3d"]}, head, "t")
    ema = hub.handle(
        "POST", "/api/teacher/player", {}, {"name": "Ema", "picture": "cat"}, head, "t"
    )
    leo = hub.handle(
        "POST", "/api/teacher/player", {}, {"name": "Leo", "picture": "dog"}, head, "t"
    )

    def state(player):
        return hub.handle("GET", "/api/class/state", {"profile": player["id"]}, {}, code, "c")

    assert (state(ema)["views"], state(ema)["lang"]) == (["3d"], "sk")  # the class's
    body = {"profile": ema["id"], "views": "2d", "lang": "device"}
    assert hub.handle("POST", "/api/teacher/player/settings", {}, body, head, "t") == {
        "views": ["2d"],
        "lang": None,
    }
    assert (state(ema)["views"], state(ema)["lang"]) == (["2d"], None)  # Ema's own
    assert (state(leo)["views"], state(leo)["lang"]) == (["3d"], "sk")  # Leo: the class's
    players = hub.handle("GET", "/api/teacher/overview", {}, {}, head, "t")["players"]
    assert {p["name"]: p["own"] for p in players} == {
        "Ema": {"views": ["2d"], "lang": None},
        "Leo": {},
    }
    body = {"profile": ema["id"], "views": "class"}
    hub.handle("POST", "/api/teacher/player/settings", {}, body, head, "t")
    assert state(ema)["views"] == ["3d"] and state(ema)["lang"] is None  # lang still her own
    for wrong in ({"views": "4d"}, {"lang": "de"}, {"profile": "p00000000", "views": "2d"}):
        with pytest.raises(Exception):  # noqa: B017 - ClassError or ProfileError
            hub.handle(
                "POST",
                "/api/teacher/player/settings",
                {},
                {"profile": ema["id"], **wrong},
                head,
                "t",
            )
    hub.handle("POST", "/api/teacher/player/remove", {}, {"profile": ema["id"]}, head, "t")
    assert ema["id"] not in classes.player_settings("5.D")
