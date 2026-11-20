"""The local web server: static files and the JSON API, over real HTTP on localhost."""

import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mse_codezoo import ir
from mse_codezoo import server as server_module
from mse_codezoo.profiles import ProfileStore
from mse_codezoo.server import MAX_BODY, CodeZooServer

PROGRAM_SCHEMA = Draft202012Validator(ir.json_schema())


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    # a throwaway data folder: tests never touch the real players on this computer
    store = ProfileStore(tmp_path_factory.mktemp("codezoo-home"))
    server = CodeZooServer("127.0.0.1", 0, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # 127.0.0.1, not "localhost": on Windows the IPv6 attempt for localhost adds ~2 s per request
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def request(base_url, path, body=None, raw=None, method=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base_url + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def get_json(base_url, path, body=None, **kwargs):
    status, _, payload = request(base_url, path, body, **kwargs)
    return status, json.loads(payload)


def test_index_page_is_served(base_url):
    status, headers, payload = request(base_url, "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"<title>CodeZoo</title>" in payload


@pytest.mark.parametrize("name", ["app.js", "blocks.js", "stage.js", "code.js", "api.js"])
def test_scripts_are_served_as_javascript(base_url, name):
    status, headers, _ = request(base_url, f"/{name}")
    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")


def test_vendored_blockly_is_served(base_url):
    status, headers, payload = request(base_url, "/vendor/blockly/blockly.min.js")
    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")
    assert len(payload) > 500_000
    status, headers, _ = request(base_url, "/vendor/blockly/media/sprites.svg")
    assert status == 200
    assert headers["Content-Type"].startswith("image/svg+xml")


def test_page_needs_no_internet():
    """Everything the page loads must come from the package, so it works offline."""
    web = Path(server_module.WEB_DIR)
    index = (web / "index.html").read_text(encoding="utf-8")
    assert not re.findall(r"""(?:src|href)=["']https?://""", index)
    assert 'media: "vendor/blockly/media/"' in (web / "blocks.js").read_text(encoding="utf-8")
    vendor = web / "vendor" / "blockly"
    assert (vendor / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")
    assert (vendor / "media" / "sprites.svg").is_file()
    three = web / "vendor" / "three"
    assert (three / "LICENSE").read_text(encoding="utf-8").startswith("The MIT License")
    stage = (web / "stage3d.js").read_text(encoding="utf-8")
    assert 'from "./vendor/three/three.module.min.js"' in stage
    for script in web.glob("*.js"):  # no module is fetched from a CDN
        assert not re.findall(r"""from ["']https?://""", script.read_text(encoding="utf-8"))


def test_vendored_three_is_served_as_a_module(base_url):
    status, headers, payload = request(base_url, "/vendor/three/three.module.min.js")
    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")
    assert b'const t="170"' in payload[:400]


@pytest.mark.parametrize(
    "path", ["/../pyproject.toml", "/%2e%2e/server.py", "/..%2fserver.py", "/missing.js"]
)
def test_files_outside_the_web_folder_are_not_served(base_url, path):
    status, _, _ = request(base_url, path)
    assert status == 404


def test_levels_list(base_url):
    status, levels = get_json(base_url, "/api/levels")
    assert status == 200
    first = {
        "id": "m01-l01",
        "title": "One banana",
        "module": "sequences",
        "animal": "monkey",
        "signature": False,
        "worlds": 1,
    }
    assert first in levels


def test_level_detail(base_url):
    status, level = get_json(base_url, "/api/levels/m01-l03")
    assert status == 200
    assert level["world"]["walls"] == [[1, 0]]
    assert level["world"]["items"] == [[2, 0, "B"]]
    assert level["world"]["position"] == [0, 0] and level["world"]["facing"] == "east"
    assert level["pack"]["actions"]["grab"] == "grab"
    assert level["unlockedBlocks"] == ["step", "turn_left", "turn_right", "grab"]


def test_unknown_level_is_404(base_url):
    status, data = get_json(base_url, "/api/levels/m99-l99")
    assert status == 404
    assert "No level called" in data["error"]


def test_parse(base_url):
    status, data = get_json(base_url, "/api/parse", {"source": "step(1)\nclass Jump:\n    pass\n"})
    assert status == 200
    assert data["ok"] is True
    assert PROGRAM_SCHEMA.is_valid(data["program"])
    assert data["program"]["body"][1]["type"] == "RawCode"
    assert data["diagnostics"][0]["severity"] == "warning"
    first = data["program"]["body"][0]["id"]
    assert data["positions"][first]["line"] == 1


def test_parse_syntax_error(base_url):
    status, data = get_json(base_url, "/api/parse", {"source": "step(\n"})
    assert status == 200
    assert data["ok"] is False and data["program"] is None
    assert data["diagnostics"][0]["line"] == 1


def test_print_round_trips_a_program_from_blocks(base_url):
    program = {
        "type": "Program",
        "id": "program",
        "body": [
            {
                "type": "For",
                "id": "b1",
                "target": {"type": "Name", "id": "b1.var", "name": "i"},
                "iter": {
                    "type": "Call",
                    "id": "b1.range",
                    "func": "range",
                    "args": [{"type": "Const", "id": "b1.count", "value": 5}],
                },
                "body": [
                    {
                        "type": "ExprStmt",
                        "id": "b2",
                        "value": {"type": "Call", "id": "b2.call", "func": "grab", "args": []},
                        "comment": "yum",
                    }
                ],
            }
        ],
    }
    assert PROGRAM_SCHEMA.is_valid(program)
    status, data = get_json(base_url, "/api/print", {"program": program})
    assert status == 200
    assert data["text"] == "for i in range(5):\n    grab()  # yum\n"
    assert data["sourceMap"]["b1"]["line"] == 1
    assert data["sourceMap"]["b2"]["line"] == 2


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"program": "step(1)"},
        {"program": {"type": "Teleport"}},
        {"program": {"type": "Name", "id": "x", "name": "a"}},
        {"program": {"type": "Program", "id": "p", "body": [{"type": "ExprStmt", "id": "s"}]}},
    ],
)
def test_print_rejects_bad_programs(base_url, body):
    status, data = get_json(base_url, "/api/print", body)
    assert status == 400
    assert data["error"]


def test_run(base_url):
    body = {"level": "m01-l01", "source": "step(4)\ngrab()\n"}
    status, data = get_json(base_url, "/api/run", body)
    assert status == 200
    assert data["ok"] is True
    assert data["check"]["solved"] is True
    assert [step["line"] for step in data["steps"]] == [1, 2]
    assert data["steps"][0]["events"][-1] == {"type": "move", "from": [3, 0], "to": [4, 0]}


def test_run_error_has_a_line(base_url):
    status, data = get_json(base_url, "/api/run", {"level": "m01-l03", "source": "step(2)\n"})
    assert status == 200
    assert data["ok"] is False
    assert data["error"]["line"] == 1
    assert data["error"]["message"].startswith("Bump!")


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/api/run", {"level": "m01-l01"}, 400),
        ("/api/run", {"level": "nope", "source": ""}, 404),
        ("/api/parse", {"source": 5}, 400),
        ("/api/nothing", {}, 404),
    ],
)
def test_api_errors(base_url, path, body, status):
    got, data = get_json(base_url, path, body)
    assert got == status
    assert data["error"]


def test_bad_json_and_huge_bodies_are_rejected(base_url):
    status, data = get_json(base_url, "/api/parse", raw=b"{not json")
    assert status == 400 and "JSON" in data["error"]
    status, _ = get_json(base_url, "/api/parse", raw=b"[1, 2]")
    assert status == 400
    status, _ = get_json(base_url, "/api/parse", raw=b"x" * (MAX_BODY + 1))
    assert status == 413


# --- players and grown-ups -------------------------------------------------------------


def test_players_progress_time_and_grown_ups(base_url):
    status, data = get_json(base_url, "/api/profiles")
    assert status == 200
    assert "fox" in data["pictures"]
    assert data["parent"] == {"dailyMinutes": None, "privateMode": False, "hasPin": False}

    status, ema = get_json(base_url, "/api/profiles", {"name": "Ema", "picture": "fox"})
    assert status == 200 and ema["name"] == "Ema"
    status, data = get_json(base_url, "/api/profiles", {"name": "ema", "picture": "owl"})
    assert status == 400 and "already" in data["error"]

    body = {"level": "m01-l01", "source": "step(4)\ngrab()\n", "profile": ema["id"]}
    status, run = get_json(base_url, "/api/run", body)
    assert status == 200 and run["progress"]["stars"] == 3

    status, progress = get_json(base_url, f"/api/profiles/{ema['id']}/progress")
    assert progress["levels"] == {"m01-l01": {"stars": 3, "solved": True}}
    assert progress["today"]["over"] is False

    status, data = get_json(base_url, "/api/parent/settings", {"newPin": "2468", "dailyMinutes": 1})
    assert status == 200 and data["hasPin"] is True
    status, data = get_json(base_url, "/api/parent/settings", {"dailyMinutes": 30})
    assert status == 403
    status, data = get_json(base_url, "/api/parent/check", {"pin": "0000"})
    assert status == 403 and "not right" in data["error"]
    status, today = get_json(base_url, f"/api/profiles/{ema['id']}/time", {"seconds": 60})
    assert today["over"] is True

    status, report = get_json(base_url, "/api/parent/report", {"pin": "2468", "profile": ema["id"]})
    assert status == 200 and report["levelsSolved"] == 1
    status, exported = get_json(base_url, "/api/parent/export", {"pin": "2468", "profile": "Ema"})
    assert exported["format"] == "codezoo-profile"
    status, _ = get_json(base_url, "/api/parent/remove", {"profile": "Ema"})
    assert status == 403
    status, data = get_json(base_url, "/api/parent/remove", {"pin": "2468", "profile": "Ema"})
    assert status == 200 and data["removed"]["name"] == "Ema"
    status, _ = get_json(base_url, "/api/parent/settings", {"pin": "2468", "clearPin": True})
    assert status == 200


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/api/profiles", {"name": "Tom", "picture": "dragon"}, 400),
        ("/api/profiles/p00000000/time", {"seconds": 30}, 400),
        ("/api/profiles/p00000000/time", {"seconds": "lots"}, 400),
        ("/api/parent/fly", {}, 404),
        ("/api/run", {"level": "m01-l01", "source": "", "profile": "nobody"}, 400),
    ],
)
def test_player_api_errors(base_url, path, body, status):
    got, data = get_json(base_url, path, body)
    assert got == status
    assert data["error"]


def test_unknown_profile_progress_is_404_shaped(base_url):
    status, _, _ = request(base_url, "/api/profiles/../progress")
    assert status == 404
    status, data = get_json(base_url, "/api/profiles/p00000000/progress")
    assert status == 400 and "No player" in data["error"]


def test_language_from_query_and_body(base_url):
    status, level = get_json(base_url, "/api/levels/m05-l02?lang=sk")
    assert status == 200
    assert level["title"] == "Zrelý alebo zhnitý"
    assert level["pack"]["animalName"] == "opička"
    status, data = get_json(
        base_url, "/api/run", {"level": "m01-l03", "source": "step(5)\n", "lang": "sk"}
    )
    assert data["check"]["message"] == "Bum! Tu stojí skala, ďalej sa nedá."
    _, english = get_json(base_url, "/api/levels/m05-l02")
    assert english["title"] == "Ripe or rotten"


def test_run_in_another_world(base_url):
    body = {"level": "m05-l02", "source": "step(1)\ngrab()\n", "variant": 1}
    status, data = get_json(base_url, "/api/run", body)
    assert status == 200
    assert data["variant"] == 1
    assert data["world"]["collected"] == {"R": 1}
    assert data["feeling"]["mood"] == "puzzled"
    status, data = get_json(base_url, "/api/run", {**body, "variant": "2"})
    assert status == 400
