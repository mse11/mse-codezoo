"""The console: print() leaves an event on its step, so the page can show it as the run plays."""

from pathlib import Path

from mse_codezoo import interpreter
from mse_codezoo.lang_python import parse

WEB = Path(__file__).parents[1] / "mse_codezoo" / "web"


def printed_events(source):
    result = interpreter.run(parse(source).program)
    return result, [e["text"] for s in result.steps for e in s.events if e["type"] == "print"]


def test_each_print_leaves_its_text_on_its_step():
    result, texts = printed_events('print("start")\nx = 2\nprint("x is", x, end="!")\nprint()\n')
    assert texts == ["start\n", "x is 2!", "\n"]
    assert result.output == ["start", "x is 2!"]  # the whole output is unchanged
    assert "".join(texts) == "\n".join(result.output) + "\n"


def test_print_inside_a_function_and_a_loop():
    source = "def hello(n):\n    print('hi', n)\nfor i in range(2):\n    hello(i)\n"
    _result, texts = printed_events(source)
    assert texts == ["hi 0\n", "hi 1\n"]


def test_the_page_has_a_console_pane_next_to_the_code():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert page.index('data-pane="code"') < page.index('data-pane="console"')
    assert 'data-tab="console"' in page  # phones get a Console tab
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'event.type === "print"' in script
    assert 'class: "printed"' not in script  # no second copy under the stage
    for stage in ("stage.js", "stage3d.js"):  # the stages don't wait on print events
        assert '"return", "print"]' in (WEB / stage).read_text(encoding="utf-8")


def test_the_result_sits_next_to_the_goal():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    head = page[page.index('class="stage-head"') : page.index('class="stage-tools"')]
    assert 'id="goal"' in head and 'id="result"' in head and 'id="feeling"' in head


def test_each_pane_has_zoom_buttons_and_ctrl_wheel():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "setupBlocksZoom(" in script and script.count("setupZoom(") == 5
    for name in ('"code"', '"console"', 'name: "stage"', 'name: "head"'):
        assert name in script
    zoom = (WEB / "zoom.js").read_text(encoding="utf-8")
    assert "event.ctrlKey" in zoom and "passive: false" in zoom
    assert "controls: false" in (WEB / "blocks.js").read_text(encoding="utf-8")
    page = (WEB / "index.html").read_text(encoding="utf-8")
    # titles keep their text in a span, so translating the page leaves the buttons alone
    assert '<div class="pane-title" data-i18n>' not in page


def test_step_and_reset_have_icons_that_survive_translation():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    for button in ('id="step"', 'id="reset"'):
        start = page.index(button)
        assert 'class="icon"' in page[start : page.index("</button>", start)]


def test_errors_show_in_the_console_too():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert script.count("problemsToConsole(run);") == 2  # a stopped run, and code Python can't read
    assert "console-error" in (WEB / "style.css").read_text(encoding="utf-8")


def test_goal_and_result_can_sit_beside_the_stage():
    look = (WEB / "look.js").read_text(encoding="utf-8")
    assert 'layout: "auto"' in look and "root.dataset.layout = layout()" in look
    for choice in ('["auto",', '["above",', '["side",'):
        assert choice in look
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert 'html[data-layout="side"] .stage-pane {' in css


def test_a_bar_between_the_stage_and_the_goal_column():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="split-head"' in page and 'role="separator"' in page
    layout = (WEB / "layout.js").read_text(encoding="utf-8")
    assert "headSplit" in layout and '"--head-w"' in layout
    assert 'headSplit: $("split-head")' in (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "#split-head { display: none; }" in css  # only beside the stage


def test_ctrl_wheel_never_zooms_the_whole_page():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "keepPageZoom();" in script
    assert 'name: "bar"' in script  # the top bar has its own Ctrl + wheel zoom
    stage = script[script.index('name: "stage"') - 300 : script.index('name: "stage"')]
    assert 'area: document.querySelector(".stage-pane")' in stage  # not just the picture
    look = (WEB / "look.js").read_text(encoding="utf-8")
    assert "resetAllZoom" in look


def test_a_bar_between_the_code_and_the_console():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert (
        page.index('data-pane="code"')
        < page.index('id="split-console"')
        < page.index('data-pane="console"')
    )
    layout = (WEB / "layout.js").read_text(encoding="utf-8")
    assert "consoleSplit" in layout and '"--console-w"' in layout
    assert 'consoleSplit: $("split-console")' in (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert '"blocks vsplit code csplit console"' in css


def test_zoom_reaches_far_and_titles_zoom_together():
    zoom = (WEB / "zoom.js").read_text(encoding="utf-8")
    assert "const MAX = 4;" in zoom and "const MIN = 0.4;" in zoom
    assert "maxScale: 4" in (WEB / "blocks.js").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'name: "titles", variable: "--title-zoom"' in script
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "font-size: calc(1rem * var(--title-zoom, 1));" in css


def test_the_top_bar_is_in_groups():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    header = page[page.index("<header") : page.index("</header>")]
    # first row: the modes, then the player's group and the grown-ups;
    # second row: the level together with the buttons that run it
    run = header[header.index("run-group") :]
    assert 'id="run"' in run and 'id="step"' in run and 'id="speed"' in run
    assert 'id="level-select"' in run
    assert header.index("user-group") < header.index("bar-break") < header.index("run-group")
    user = header[header.index("user-group") : header.index("bar-break")]
    for part in (
        'id="player"',
        'id="animal-select"',
        'id="python-select"',
        'id="lang"',
        'id="zoo"',
    ):
        assert part in user
    modes = header[header.index('class="modes"') : header.index("user-group")]
    assert 'href="editor.html"' in modes and 'href="game.html"' in modes
    # the language as a drawn flag and its code: a flag emoji reads "SK SK" on Windows
    for page in ("app.js", "game.js"):
        assert "fillLangSelect(" in (WEB / page).read_text(encoding="utf-8")
    i18n = (WEB / "i18n.js").read_text(encoding="utf-8")
    assert "export function fillLangSelect" in i18n and "image/svg+xml" in i18n


def test_the_player_and_their_animal_are_one_control():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert "function playerAnimal(profile)" in script
    page = (WEB / "index.html").read_text(encoding="utf-8")
    pick = page[
        page.index('class="player-pick"') : page.index("</span>", page.index('class="player-pick"'))
    ]
    assert 'id="player"' in pick and 'id="animal-select"' in pick  # one control, emoji once


def test_one_button_puts_every_zoom_and_bar_back():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    user = page[page.index("user-group") : page.index("bar-break")]
    assert 'id="reset-view"' in user
    assert '$("reset-view").addEventListener("click", resetAllZoom)' in (WEB / "app.js").read_text(
        encoding="utf-8"
    )
    assert '"codezoo-zoom-reset"' in (WEB / "layout.js").read_text(encoding="utf-8")


def test_a_player_can_change_their_picture_without_a_new_player(tmp_path):
    from mse_codezoo.profiles import ProfileError, ProfileStore
    from mse_codezoo.server import dispatch

    store = ProfileStore(tmp_path)
    tato = store.add("tato", "monkey")
    changed = dispatch("POST", f"/api/profiles/{tato.id}/picture", {}, {"picture": "fox"}, store)
    assert changed["picture"] == "fox" and changed["name"] == "tato"
    assert [p.picture for p in store.profiles()] == ["fox"]  # still one player
    import pytest

    with pytest.raises(ProfileError):
        store.set_picture(tato.id, "dragon-king")
    players = (WEB / "players.js").read_text(encoding="utf-8")
    assert "changePicture(" in players and "api.setPicture(" in players


def test_every_page_has_the_three_modes_after_the_logo():
    for page, current in (
        ("index.html", "index.html"),
        ("editor.html", "editor.html"),
        ("game.html", "game.html"),
    ):
        html = (WEB / page).read_text(encoding="utf-8")
        logo = html.index('class="logo"')
        nav = html[html.index('class="modes"') : html.index("</nav>", html.index('class="modes"'))]
        assert html.index('class="modes"') > logo
        for href in ("index.html", "editor.html", "game.html"):
            assert f'href="{href}"' in nav
        assert f'href="{current}" aria-current="page"' in nav


def test_the_code_panes_colour_python_in_the_colours_of_the_blocks():
    """Each word in the code has its block's colour (syntax.js under the textarea), on the
    main page and the game page; nothing is loaded from elsewhere."""
    import re

    syntax = (WEB / "syntax.js").read_text(encoding="utf-8")
    assert "export function highlightPython(text)" in syntax
    assert "export function colourTextarea(textarea)" in syntax
    assert "export function setCommandNames(actions = {})" in syntax
    assert "import " not in syntax and "http" not in syntax
    blocks = (WEB / "blocks.js").read_text(encoding="utf-8")
    colours = dict(re.findall(r"^  (\w+): \"(#[0-9A-Fa-f]{6})\",$", blocks, re.MULTILINE))
    css = (WEB / "style.css").read_text(encoding="utf-8")
    dark = css[css.index(':root[data-theme="dark"] {\n  --blk-motion') :]
    for family in (
        "motion",
        "action",
        "say",
        "sensor",
        "loop",
        "logic",
        "variable",
        "math",
        "trick",
        "note",
    ):
        assert f".syn-{family} {{ color: var(--blk-{family});" in css, family
        # the dark theme uses the very colours of the blocks
        assert f"--blk-{family}: {colours[family]};" in dark, family
    for word, family in (
        ("step", "motion"),
        ("grab", "action"),
        ("for", "loop"),
        ("if", "logic"),
        ("print", "say"),
    ):
        assert re.search(rf'{family}: \[[^\]]*"{word}"', syntax), word
    code = (WEB / "code.js").read_text(encoding="utf-8")
    assert "setCommandNames(actions)" in code  # the penguin's catch() is coloured like grab
    assert "code.setCommands(level.pack.actions)" in (WEB / "app.js").read_text(encoding="utf-8")
    assert 'colourTextarea($("source"))' in (WEB / "game.js").read_text(encoding="utf-8")
    assert ".code-area textarea.coloured { color: transparent; caret-color: var(--text); }" in css
