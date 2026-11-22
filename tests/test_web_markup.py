"""Every web page has well-formed markup: no id twice, and every tag closed where it opened.

A leftover from moving a section once put a second copy of a list (with the same id) outside
its card on the teacher's screen; the script filled only the first copy.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).parents[1] / "mse_codezoo" / "web"
PAGES = sorted(WEB.glob("*.html"))
EMPTY = {"input", "meta", "link", "br", "img", "hr", "source", "wbr"}


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.open: list[tuple[str, int]] = []
        self.wrong: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in EMPTY:
            self.open.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag: str) -> None:
        if tag in EMPTY:
            return
        if not self.open or self.open[-1][0] != tag:
            self.wrong.append(f"</{tag}> on line {self.getpos()[0]}")
            return
        self.open.pop()


def test_there_are_pages():
    assert {"index.html", "teacher.html", "editor.html", "check.html"} <= {p.name for p in PAGES}


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_id_twice(page):
    ids = re.findall(r'\bid="([^"]+)"', page.read_text(encoding="utf-8"))
    assert sorted({i for i in ids if ids.count(i) > 1}) == []


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_tag_is_closed_where_it_opened(page):
    tags = Tags()
    tags.feed(page.read_text(encoding="utf-8"))
    tags.close()
    assert tags.wrong == []
    assert [f"<{tag}> from line {line}" for tag, line in tags.open] == []
