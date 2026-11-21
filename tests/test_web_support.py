"""The donation link appears only where grown-ups are: never on a child's screen.

Allowed: the Grown-ups panel in index.html (shown only after the gate) and the teacher's
screen. Kid-safety seals forbid payment prompts aimed at children (IMPLEMENTATION_PLAN.md,
Future improvements 3).
"""

import re
from pathlib import Path

WEB = Path(__file__).parents[1] / "mse_codezoo" / "web"
LINK = "buymeacoffee.com"


def test_the_link_is_only_in_the_grown_ups_panel_and_the_teachers_screen():
    found = {p.name for p in WEB.glob("*.*") if LINK in p.read_text(encoding="utf-8")}
    assert found == {"index.html", "teacher.html"}


def test_in_the_game_page_it_sits_inside_the_grown_up_panel():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert page.count(LINK) == 1
    panel = re.search(r'<div id="grownup-panel".*?</dialog>', page, re.DOTALL)
    assert panel and LINK in panel.group(0)
    assert 'id="grownup-panel" class="grownup-panel" hidden' in page  # hidden until the gate


def test_the_link_opens_a_new_tab_without_telling_who_clicked():
    for name in ("index.html", "teacher.html"):
        page = (WEB / name).read_text(encoding="utf-8")
        tag = re.search(rf'<a[^>]*{re.escape(LINK)}[^>]*>', page).group(0)
        assert 'target="_blank"' in tag and "noreferrer" in tag
