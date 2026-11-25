"""The web client's own texts (web/i18n.js) have a Slovak translation for every t("...")
call and every data-i18n label in the pages."""

import json
import re
from pathlib import Path

WEB = Path(__file__).parents[1] / "mse_codezoo" / "web"
T_CALL = re.compile(r'\bt\("((?:[^"\\]|\\.)*)"')
SK_ENTRY = re.compile(r'^\s*("(?:[^"\\]|\\.)*")\s*:\s*"', re.MULTILINE)
DATA_I18N = re.compile(r"<([a-z0-9]+)[^>]*\sdata-i18n(?:\s[^>]*)?>([^<]+)<")
DATA_LABEL = re.compile(r'data-i18n-(?:label|title)="([^"]+)"')


def sk_keys() -> set[str]:
    text = (WEB / "i18n.js").read_text(encoding="utf-8")
    block = text[text.index("const SK = {") : text.index("const CONCEPTS")]
    return {json.loads(key) for key in SK_ENTRY.findall(block)}


def used_texts() -> set[str]:
    found = set()
    for path in WEB.glob("*.js"):
        if path.name == "i18n.js":
            continue
        for raw in T_CALL.findall(path.read_text(encoding="utf-8")):
            found.add(json.loads(f'"{raw}"'))
    for path in WEB.glob("*.html"):
        page = path.read_text(encoding="utf-8")
        found |= {text.strip() for _tag, text in DATA_I18N.findall(page) if text.strip()}
        found |= set(DATA_LABEL.findall(page))
    return found


def test_every_web_text_has_a_slovak_translation():
    missing = sorted(used_texts() - sk_keys() - {"3D", "2D"})
    assert not missing, f"add these to SK in mse_codezoo/web/i18n.js: {missing}"


def test_the_pane_toggles_are_beside_the_modes():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    modes_end = page.index("</nav>", page.index('class="modes"'))
    group = page.index('class="pane-toggles"')
    assert modes_end < group < page.index('id="class-name"')
    for pane in ("blocks", "code", "console"):
        assert f'data-show="{pane}"' in page
    layout = (WEB / "layout.js").read_text(encoding="utf-8")
    assert "export function setupPaneToggles" in layout and "setAllowed" in layout
