# mse-codezoo

CodeZoo teaches real Python through small animal coding games. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the full plan.

The engine is a pure-Python package (`mse_codezoo/`, standard library only) with a [click](https://click.palletsprojects.com/) command line, `codezoo`. Only `cli.py` may import click; `tests/test_engine_stdlib.py` enforces that so the engine can later run in Pyodide.

## Development

Needs [uv](https://docs.astral.sh/uv/). The package supports Python 3.11+; development is pinned to 3.14 in `.python-version`.

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run ruff check
```

```bash
uv run codezoo --help
```

## Web UI

```bash
uv run codezoo serve --open
```

Opens `http://localhost:8765/` with three panes: the stage, Blockly blocks and the Python code, kept in sync through the engine. Drag blocks and the code appears; tick "let me type" to edit the code and the blocks follow. Run or Step to watch the animal, with the current line and block lit up. Drag the bars between the panes to resize them. Everything the page needs ships in the package, so it works offline.

**Animals.** The monkey, the penguin, the beaver and the fox. Core levels can be played by any animal (pick it next to the level list): the program, the hints and the items follow it, so the penguin `catch()`es fish where the monkey `grab()`s bananas. Signature levels belong to one animal and use its tricks: the monkey `swing()`s across gaps and `climb()`s trees, the penguin `slide()`s until something is in the way (and thin ice raises `CrackError`), the beaver picks up logs and `build()`s a dam (`inventory()` says what it carries), and the fox `sniff()`s the open ways and `hide()`s from guards (`guard_ahead()`).

**Stage.** A low-poly 3D world for each animal, drawn with three.js; untick "3D" for the flat 2D stage (also used automatically where WebGL is missing). Levels with several worlds show World 1, World 2... buttons: the program must solve every world, which is what makes `if` worth learning. While a program runs, the call stack shows under the stage as nested burrows, one per function that is still running. After each run the animal shows how it feels (proud, happy, puzzled, oops, confused, dizzy) with a short, kind message.

**Languages.** English and Slovak: the language menu switches the page, block labels, level titles, hints and every engine message. Python keywords and commands (`for`, `step`) stay English. The CLI takes `--lang sk` (or `CODEZOO_LANG=sk`).

**Players and grown-ups.** Each child picks their picture; stars and progress are saved per player. "Just try it" plays without saving. The Grown-ups button opens a gate (a sum in words, plus a PIN if one is set) with the daily time limit, private mode, a learning report per player, export and remove.

**After a run.** "Make a storybook" turns the run into printable picture pages (type a title and your own line on each page, then print); "Save this run" downloads it as a `.run.json` file for `codezoo replay` and `codezoo story export`. An uncaught error shows where it happened, from the outside in, like Python's traceback.

**My zoo.** Solving levels earns stickers (first level, every finished module, 10/30/60/100 stars, every card played away from the screen). Drag them around the animal's habitat and dress the animal up (more stickers unlock more outfits); the outfit shows on the stage. Printable unplugged cards (one per module and animal) carry a word code and a QR code: type the code, or scan the card where the browser can read QR codes (the picture never leaves the device), to get the card's sticker and open its level. After three failed tries on a level, CodeZoo offers an easier level that practises the same idea; the child can still pick any level.

**Level editor.** `editor.html` (the "Level editor" link) is a prototype: paint a world, choose the goal, write a reference solution, and "Test the level" asks the engine to check it like `codezoo levels validate`; then download the level JSON and solution file.

**Where data lives.** Only on this computer, as JSON files: `%APPDATA%\CodeZoo` on Windows, `~/Library/Application Support/CodeZoo` on macOS, `~/.local/share/codezoo` on Linux. Set `CODEZOO_HOME` or use `codezoo serve --data-dir PATH` to keep it elsewhere (for example a separate folder per classroom).

## Play in the terminal

For adult beginners (and anyone who prefers a text editor): each level gets a `.py` file; edit it, save, and watch the monkey on a coloured character grid.

```bash
uv run codezoo play --profile Ema
```

Keys: `r` run, `e` open the file in `$EDITOR` and run it, `w` rerun every time the file is saved, `h` next hint, `n`/`p` next or previous level, `l` level list, `1`-`9` pick a world, `q` quit. Without `--level` it starts at the player's first unsolved level; the daily limit from `codezoo parent set` applies.

## Try it

Look at a level, then check a program for it. [playground/](playground/README.md) has an example for every level, plus `oops/` programs that show the error messages.

```bash
uv run codezoo levels show m01-l01
```

```bash
uv run codezoo check m01-l01 playground/m01-l01.py
```

```bash
uv run codezoo run m01-l03 playground/m01-l03.py --trace
```

## Layout

```
mse_codezoo/        the package (flat layout, no src/)
  ir.py             language-neutral program model, JSON (de)serialisation
  ir.schema.json    JSON Schema of the IR, generated by `codezoo schema` (tests keep it in sync)
  lang_python.py    ast -> IR, printer with source map, block labels
  interpreter.py    step-by-step evaluator with limits; no exec/eval
  world.py          grid world, neutral actions and sensors, animal packs
  goals.py          goal checks and stars
  levels.py         level and pack loading (worlds, translations), structural validation
  game.py           parse + run + check one level in all its worlds
  feelings.py       how the animal feels about a run
  i18n.py           message translation (current language per request)
  locale/sk.json    Slovak messages, keyed by the English text
  term.py           terminal stage for `codezoo play` and `codezoo replay`
  runs.py           saved runs (.run.json)
  story.py          storybook pages from a saved run (printable HTML)
  cards.py          printable unplugged cards with unlock codes
  qr.py             small QR code encoder for the cards
  profiles.py       players, progress, daily time, grown-up settings (local JSON files)
  server.py         stdlib HTTP server and JSON API behind `codezoo serve`
  web/              browser client: app.js, blocks.js (Blockly <-> IR), stage3d.js (three.js),
                    stage.js (2D), code.js, i18n.js (EN/SK), players.js (picker, grown-ups,
                    goodbye), layout.js (splitters), editor.html/js (level editor)
  cli.py            click commands (the only module importing click)
  content/levels/   level JSON + reference solutions (<file>.solution.py)
  content/animals/  animal packs
tests/              includes test_differential.py: our interpreter vs CPython
scripts/            pyodide_smoke.mjs: the engine and every level inside Pyodide (CI)
```

## Commands

| Command | What it does |
| --- | --- |
| `codezoo play [--level ID] [--profile NAME] [--dir PATH] [--speed 1-5]` | Terminal game: edit a `.py` file, run it, watch the grid |
| `codezoo run LEVEL PROGRAM.py [--trace] [--json] [--animal NAME]` | Runs a program in a level; `--trace` shows every step and the grid |
| `codezoo check LEVEL PROGRAM.py [--profile NAME]` | Goal, stars and a hint; exit code 0 only when solved; `--profile` saves the result |
| `codezoo blocks PROGRAM.py` | Block outline with each block's lines and node id |
| `codezoo serve [--port 8765] [--open] [--data-dir PATH]` | Local web UI with stage, blocks and code |
| `codezoo profile list/add/remove/export/import` | Players on this computer; `add NAME --picture fox` |
| `codezoo parent show/set/pin/report` | Grown-up settings: `set --daily-minutes 30 --private`, `pin`, `report NAME` |
| `codezoo run ... --save RUN.json` | Also saves the run for `replay` and `story export` |
| `codezoo replay RUN` | Replays a saved run on the terminal grid |
| `codezoo story export RUN -o story.html` | A printable storybook of a saved run |
| `codezoo cards print --animal NAME -o cards.html` | Printable unplugged cards with codes and QR codes |
| `codezoo cards unlock CODE --profile NAME` | Unlocks a card's sticker |
| `codezoo world new ANIMAL [--content DIR]` | Scaffolds `SPEC.md`, `pack.json` and a first level for a new animal |
| `codezoo schema [-o FILE]` | JSON Schema of the program model (IR), the contract with the web client |
| `codezoo levels list` | Bundled levels |
| `codezoo levels show LEVEL [--solution]` | One level: goal, star rules, blocks, grid and hints; `--solution` adds the reference solution |
| `codezoo levels validate [--all] [PATHS...]` | Checks level files and that each reference solution earns every star |

`LEVEL` is a level id (`m01-l01`) or a path to a level `.json` file. A program may `import` helper files that sit next to it (your own `tricks.py`), and the files a level brings with it. Every command takes `--lang en|sk` before the command name, for example `codezoo --lang sk check ...`.

## Supported Python (phase 3)

Phase 2: calls, variables, `=` and `+=`-style updates, `for` and `while` loops, `if`/`elif`/`else`, comparisons (also chained, `is`, `in`), `and`/`or`/`not`, `x if c else y`, `+ - * / // % **`, numbers, text, `True`/`False`/`None`, f-strings (with `!r` and format specs), indexing and slicing, text methods, comments and `pass`.

Phase 3 adds:

- **Loops II:** `break`, `continue`, loops inside loops.
- **Functions:** `def` with inputs, default values and keyword arguments, `return` (also several values at once), local names and `global`, functions inside functions, and `import` / `from ... import` of helper files. Recursion works up to 40 calls deep, with a friendly "does it have a base case?" message beyond that.
- **Errors:** `try` / `except` (one error, several in brackets, `as e`, or bare) / `else` / `finally`, `raise`, bare `raise` inside `except`, `assert`. Errors carry real Python exceptions (`ValueError`, `TypeError`, `KeyError`, `IndexError`, `ZeroDivisionError`, `NameError`, the penguin's `CrackError`...), so `except` catches what CPython would. The zoo's own limits (steps, depth, sizes) can't be caught.
- **Collections:** lists, tuples, dictionaries (with `**` merging) and sets, indexing, slicing and assigning into them, `del`, unpacking (`a, b = b, a`, `first, *rest = ...`), `in`, `| & - ^` on sets, list/dict/set comprehensions, and the methods `append pop insert remove index extend count sort reverse clear copy`, `get setdefault update keys values items`, `add discard union intersection difference symmetric_difference issubset issuperset`, `split join`; builtins `list tuple dict set sorted sum enumerate zip reversed any all isinstance` (with `key=`/`reverse=` where Python has them).

The world adds `step turn_left turn_right grab say`, the sensors `is_blocked() item_here() item_ahead()` and each animal's tricks. Classes, `lambda`, generators, `with`, `match` and `async` are kept as raw code with a friendly note and don't run yet (phase 4).

## Levels

109 levels in ten modules: 1 Sequences (12), 2 Loops (11), 3 Variables (11), 4 Types and text (12), 5 Conditions (11), 6 Loops II (11), 7 Functions (12), 8 Errors and debugging (9), 9 Collections (10), 10 Recursion (10). Every module has debugging levels whose starter program has a bug to fix. Signature levels belong to the monkey, penguin, beaver or fox; all other levels can be played by every animal, and `codezoo levels validate --all` checks every reference solution for every animal that can play it. Goals can ask the animal to collect items, avoid some, reach a square, say exact text, or build a dam from exact logs. Every level has a Slovak title and hints.

## Third-party software

| Component | Version | Licence | Where |
| --- | --- | --- | --- |
| [Blockly](https://github.com/RaspberryPiFoundation/blockly) | 13.3.0 | Apache-2.0 | `mse_codezoo/web/vendor/blockly/` (unchanged copy, see its README and LICENSE) |
| [three.js](https://threejs.org/) | 0.170.0 (r170) | MIT | `mse_codezoo/web/vendor/three/` (unchanged copy, see its README and LICENSE) |

CodeZoo's own code is licensed under the Apache License 2.0 (see `LICENSE` and `NOTICE`); vendored components keep their own licences. Code shared earlier under the MIT licence stays available under MIT.
