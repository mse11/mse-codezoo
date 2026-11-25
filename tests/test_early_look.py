"""The saved "Look and feel" is put on the page before it is first drawn (web/early-look.js),
so a page set to dark colours doesn't flash light while its modules load."""

from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "mse_codezoo" / "web"
PAGES = ["index.html", "editor.html", "game.html", "teacher.html", "check.html"]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_loads_it_first(page):
    html = (WEB / page).read_text(encoding="utf-8")
    tag = '<script src="early-look.js"></script>'
    assert tag in html, page
    head = html[: html.index("</head>")]
    # a plain script (not a module, not deferred) before the styles and every other script
    assert head.index(tag) < head.index('<link rel="stylesheet"')
    others = [i for i in range(len(head)) if head.startswith("<script", i)]
    assert others[0] == head.index(tag)


def test_it_reads_what_look_js_saves():
    early = (WEB / "early-look.js").read_text(encoding="utf-8")
    look = (WEB / "look.js").read_text(encoding="utf-8")
    assert 'const KEY = "codezoo.look";' in look and '"codezoo.look"' in early
    for attribute in ("theme", "text", "easy", "contrast", "targets", "motion", "layout"):
        assert f"root.dataset.{attribute}" in early and f"root.dataset.{attribute}" in look, (
            attribute
        )
    assert "import " not in early and "export " not in early  # a plain script
