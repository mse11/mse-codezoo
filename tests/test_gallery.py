"""The block and command gallery (web/gallery.js): one dialog opened with 📖 from the Blocks
and the Python pane; every card shows a palette block and the Python the engine prints for
it, so the two always match."""

import re
from pathlib import Path

import pytest

from mse_codezoo.lang_python import parse, print_program

WEB = Path(__file__).resolve().parent.parent / "mse_codezoo" / "web"
BLOCKS = (WEB / "blocks.js").read_text(encoding="utf-8")
GALLERY = (WEB / "gallery.js").read_text(encoding="utf-8")
I18N = (WEB / "i18n.js").read_text(encoding="utf-8")


def palette_keys():
    body = BLOCKS[
        BLOCKS.index("const PALETTE = {") : BLOCKS.index("\n};", BLOCKS.index("const PALETTE = {"))
    ]
    return set(re.findall(r"^  (\w+): \{", body, re.M))


def test_page_has_one_gallery_opened_from_both_panes():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert (
        page.count('id="block-gallery"') == 1 and page.count('id="gallery"') == 1
    )  # the class gallery keeps its own
    assert 'data-gallery="blocks"' in page and 'data-gallery="code"' in page
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'from "./gallery.js"' in app and "blocks.addEntry" in app


def test_code_side_is_printed_by_the_engine_from_the_blocks():
    # never written by hand: the gallery sends the blocks' IR to the printer
    assert "galleryEntries" in GALLERY and "api.print" in GALLERY
    assert "export function galleryEntries" in BLOCKS and "blockToStmt(block, names)" in BLOCKS


def test_examples_are_palette_entries_of_the_same_block():
    body = BLOCKS[
        BLOCKS.index("const GALLERY_EXAMPLES = {") : BLOCKS.index(
            "\n};", BLOCKS.index("const GALLERY_EXAMPLES = {")
        )
    ]
    examples = dict(re.findall(r'^  (\w+): \{ type: "(\w+)"', body, re.M))
    assert examples, "no examples found"
    keys = palette_keys()
    for key, block_type in examples.items():
        assert key in keys, key
        assert f'{key}: {{ type: "{block_type}"' in BLOCKS, (key, block_type)


@pytest.mark.parametrize(
    "source",
    [
        "for i in range(3):\n    step(1)\n",
        "while not is_blocked():\n    step(1)\n",
        "if item_here():\n    grab()\n",
        "if is_blocked():\n    turn_left()\nelse:\n    step(1)\n",
    ],
)
def test_example_code_is_what_the_printer_prints(source):
    parsed = parse(source)
    assert parsed.ok
    assert print_program(parsed.program).text == source


def test_group_names_and_texts_have_slovak():
    names = re.findall(r'^  \w+: "([^"]+)",', GALLERY[GALLERY.index("const GROUP_NAMES") :], re.M)
    assert len(names) >= 10
    for text in names:
        assert f'"{text}":' in I18N, text


@pytest.mark.parametrize(
    "source",
    [
        'for fruit in ["apple", "pear"]:\n    say(fruit)\n',
        "def hop():\n    step(1)\n    grab()\n",
        'class Dog:\n    def bark(self):\n        say("Woof!")\n',
    ],
)
def test_more_example_code_is_what_the_printer_prints(source):
    parsed = parse(source)
    assert parsed.ok
    assert print_program(parsed.program).text == source


def test_examples_cover_the_blocks_with_room_inside():
    body = BLOCKS[BLOCKS.index("const GALLERY_EXAMPLES = {") :]
    body = body[: body.index("\n};")]
    for key in ("for_range", "while", "if", "if_else", "for_each", "def", "try", "class"):
        assert re.search(rf"^  {key}: \{{", body, re.M), key


def test_each_block_knows_the_module_that_unlocks_it():
    from mse_codezoo.game import block_modules, level_to_json
    from mse_codezoo.levels import find_level

    modules = block_modules()
    assert modules["step"] == 1 and modules["for_range"] == 2 and modules["set"] == 3
    assert modules["while"] == 6 and modules["def"] == 7 and modules["class"] == 11
    assert level_to_json(find_level("m01-l01"))["blockModules"] == modules
    assert "This one unlocks in module {n}." in GALLERY and '"Module {n}"' in I18N
