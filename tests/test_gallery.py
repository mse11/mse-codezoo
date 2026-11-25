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
