"""``codezoo build-web``: the offline browser version, as plain static files.

The page is the same web client as ``codezoo serve``; instead of a server, the engine runs
in the browser: Pyodide (CPython compiled to WebAssembly) loads in a web worker and calls
``server.dispatch()`` directly. A service worker keeps every file (and Pyodide) after the
first visit, so it then works with no network at all. Players' progress lives in the
browser (IndexedDB), never on a server. Standard library only.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from mse_codezoo import __version__
from mse_codezoo.cards import cards_html
from mse_codezoo.i18n import LANGS, use_lang
from mse_codezoo.levels import animal_names, level_files, load_level

PACKAGE = Path(__file__).parent
WEB_DIR = PACKAGE / "web"
PYODIDE_VERSION = "0.29.5"
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
SKIP = ("__pycache__", ".pyc")
WEB_SKIP = (*SKIP, "teacher.*")  # the teacher's screen needs a classroom hub (codezoo class serve)
PAGES = ("index.html", "editor.html")


def engine_zip(target: Path) -> int:
    """The engine package (code, levels, animals, translations) as a zip for Pyodide."""
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob("*")):
            relative = path.relative_to(PACKAGE)
            if path.is_dir() or relative.parts[0] == "web" or any(s in str(path) for s in SKIP):
                continue
            archive.write(path, f"mse_codezoo/{relative.as_posix()}")
            count += 1
    return count


def _offline_page(html: str, config: dict[str, str]) -> str:
    setup = (
        '<link rel="manifest" href="manifest.webmanifest">\n'
        f"  <script>window.CODEZOO_OFFLINE = {json.dumps(config)};</script>\n"
    )
    return html.replace("</head>", f"  {setup}</head>", 1)


def build(output: Path, pyodide_url: str | None = None) -> str:
    """Write the offline site into ``output``; returns a short report."""
    pyodide = pyodide_url or PYODIDE_CDN
    if not pyodide.endswith("/"):
        pyodide += "/"
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(WEB_DIR, output, ignore=shutil.ignore_patterns(*WEB_SKIP))
    modules = engine_zip(output / "engine.zip")
    config = {"pyodide": pyodide, "engine": "engine.zip", "version": __version__}
    for page in PAGES:
        path = output / page
        path.write_text(_offline_page(path.read_text(encoding="utf-8"), config), encoding="utf-8")

    levels = [load_level(p) for p in level_files()]
    for animal in animal_names():  # the cards are made here once, not by a server
        for lang in LANGS:
            with use_lang(lang):
                (output / f"cards-{animal}-{lang}.html").write_text(
                    cards_html(animal, levels), encoding="utf-8"
                )

    template = output / "sw.template.js"
    worker = template.read_text(encoding="utf-8")
    template.unlink()
    files = sorted(p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file())
    (output / "manifest.webmanifest").write_text(
        json.dumps(
            {
                "name": "CodeZoo",
                "short_name": "CodeZoo",
                "start_url": "index.html",
                "display": "standalone",
                "background_color": "#f7f5ee",
                "theme_color": "#3e6b2f",
                "icons": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    files.append("manifest.webmanifest")
    worker = worker.replace("__CACHE__", f"codezoo-{__version__}-{len(files)}").replace(
        "__FILES__", json.dumps(["./", *files])
    )
    (output / "sw.js").write_text(worker, encoding="utf-8")
    return (
        f"Built the offline CodeZoo in {output}: {len(files) + 1} files, "
        f"{modules} engine files in engine.zip, {len(levels)} levels.\n"
        f"Pyodide {PYODIDE_VERSION} comes from {pyodide} and is kept after the first visit.\n"
        "Put the folder on any static web host (GitHub Pages, Cloudflare Pages), or try it with\n"
        f"  python -m http.server --directory {output}"
    )
