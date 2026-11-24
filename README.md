# mse-codezoo

CodeZoo teaches real Python through small animal coding games. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the full plan.

The engine is a pure-Python package (`mse_codezoo/`, standard library only) with a [click](https://click.palletsprojects.com/) command line, `codezoo`. Only `cli.py` may import click; `tests/test_engine_stdlib.py` enforces that so the engine can later run in Pyodide.

### ❤️ Support

This is a hobby project maintained in my spare time. If you find this educational tool useful, you can **[buy me a coffee](https://buymeacoffee.com/mse11)** to support the work! ☕

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

**Animals.** The monkey, the penguin, the beaver, the fox, the octopus and the bee. Core levels can be played by any animal (pick it next to the level list): the program, the hints and the items follow it, so the penguin `catch()`es fish where the monkey `grab()`s bananas. Signature levels belong to one animal and use its tricks: the monkey `swing()`s across gaps and `climb()`s trees, the penguin `slide()`s until something is in the way (and thin ice raises `CrackError`), the beaver picks up logs and `build()`s a dam (`inventory()` says what it carries), the fox `sniff()`s the open ways and `hide()`s from guards (`guard_ahead()`), the octopus stretches its eight arms with `await reach(arm)` (or `stretch(arm)` in threads) while the other arms keep working, and the bee `fly()`s over rocks, water and trees.

**Stage.** A low-poly 3D world for each animal, drawn with three.js; untick "3D" for the flat 2D stage (also used automatically where WebGL is missing). Levels with several worlds show World 1, World 2... buttons: the program must solve every world, which is what makes `if` worth learning. While a program runs, the call stack shows under the stage as nested burrows, one per function that is still running. When tasks or threads run at the same time, each gets a lane under the stage on a simulated clock (steps at the same tick play together), and the timeline slider jumps to any moment of the run. After each run the animal shows how it feels (proud, happy, puzzled, oops, confused, dizzy) with a short, kind message.

**Fun.** Every step, turn, grab and bump has its own little sound, made on the spot in the browser (no sound files, works offline); grabbing several items in a row climbs a tune and shows "+1 🍌" and "×3!". Solving a level pops the stars in one by one and throws confetti (with the level's own animal and items for three stars), and solving several levels in one sitting gets a "🔥 3 levels solved!" banner. Tap the animal when nothing is running and it giggles and hops; every tenth tap it does a secret dance. The 🎵 button (or "Sounds" in Look and feel) turns the sounds off (in a class, the teacher can decide for everyone); "less motion" turns the confetti off. Nothing of this is saved or changes the stars.

**Languages.** English and Slovak: the language menu switches the page, block labels, level titles, hints and every engine message. Python keywords and commands (`for`, `step`) stay English. The CLI takes `--lang sk` (or `CODEZOO_LANG=sk`).

**Players and grown-ups.** Each child picks their picture; stars and progress are saved per player. "Just try it" plays without saving. The Grown-ups button opens a gate (a sum in words, plus a PIN if one is set) with the daily time limit, private mode, a learning report per player, export and remove.

**After a run.** "Make a storybook" turns the run into printable picture pages (type a title and your own line on each page, then print); "Save this run" downloads it as a `.run.json` file for `codezoo replay` and `codezoo story export`. An uncaught error shows where it happened, from the outside in, like Python's traceback.

**My zoo.** Solving levels earns stickers (first level, every finished module, 10/30/60/100 stars, every card played away from the screen). Drag them around the animal's habitat and dress the animal up (more stickers unlock more outfits); the outfit shows on the stage. Printable unplugged cards (one per module and animal) carry a word code and a QR code: type the code, or scan the card where the browser can read QR codes (the picture never leaves the device), to get the card's sticker and open its level. After three failed tries on a level, CodeZoo offers an easier level that practises the same idea; the child can still pick any level.

**Python release.** The menu next to the animal picks the Python release a program is written for (default: the newest this computer's Python reads). Syntax and builtins from a newer release are refused with the release that brought them. Release-island levels (3.12–3.15) show their release, and a lock where this computer can't read it.

**Level editor.** `editor.html` (the "Level editor" link): paint one or more worlds, choose the goal (collect, reach, say, print, a file's text, optionally "done by tick N"), give answers for `input()` and files for `open()`, add Slovak title and hints, and "Test the level" asks the engine to check it like `codezoo levels validate`. Then play it, copy a share link (the level travels inside the link, nothing is uploaded; it is checked again and runs only in the zoo's interpreter), keep it in this browser's "My levels", or download the level JSON and solution file.

**Where data lives.** Only on this computer, as JSON files: `%APPDATA%\CodeZoo` on Windows, `~/Library/Application Support/CodeZoo` on macOS, `~/.local/share/codezoo` on Linux. Set `CODEZOO_HOME` or use `codezoo serve --data-dir PATH` to keep it elsewhere (for example a separate folder per classroom).

## Classroom hub

For a class or a workshop: the teacher's computer runs CodeZoo on the local network, and children join from their tablets or laptops with a class code and a picture. No cloud, no accounts, nothing sent to the internet; see [docs/classroom-privacy.md](docs/classroom-privacy.md) for what is stored.

```bash
uv run codezoo class new "Saturday club" --type workshop
```

```bash
uv run codezoo class serve "Saturday club"
```

`serve` prints the address children open and the teacher's screen address, and opens the teacher's screen. It shows the class code in big letters and a QR code: children scan it with the tablet's own camera app (it holds the address and the code), or open the address and type the code.

- **Two types.** A *workshop* is one session: children pick any of 32 animal pictures (several may pick the same one) and may type a first name (without one they're called "Cat", "Cat 2"…), and ending it deletes its data. A *class* meets regularly: the teacher adds the players (`codezoo class add-player NAME CHILD --picture owl`, or on the teacher's screen), children pick themselves from the list, and the data stays. The type only sets the defaults; every setting can be changed.
- **Starts paused.** When the hub starts, children who join wait on a "Getting ready…" screen while you pick today's levels and settings; "Start the lesson" lets everyone play.
- **Stage view.** Tick 2D, 3D or both on the teacher's screen: with one ticked, every child's device uses it (2D only helps slow tablets); with both, each child can switch.
- **Sounds.** Tick 🎵 On, 🔇 Off or both on the teacher's screen: with one ticked, every child's device follows it and the 🎵 button is hidden (Off keeps a room of tablets quiet); with both, each child can switch.
- **Colours.** Tick ☀️ Light, 🌙 Dark or both the same way: with one ticked, every child's device uses it; with both, each child can switch with the ☀️/🌙 button.
- **Per child.** The class's stage view and language are the default; in the players table you can give one child their own (for example 2D on an old tablet, or English for a guest).
- **Class language.** On the teacher's screen (or `codezoo class new --class-lang sk`) the teacher can pick the language children's devices open in; the QR code and the shared link carry it (`&lang=sk`). A child can still switch, and the language menus show a flag before each language.
- **Teacher's screen.** Who joined, stars per module, who is stuck (3 or more tries on an unsolved level), minutes today, a class concept report, the most common mistakes and which levels were tried and solved. "Pause everyone" shows an "Eyes on the teacher!" screen on every device and stops runs. "Today's levels" picks levels: once saved, children see only those ("Only these levels", on by default); untick it to show the picks first under "⭐ Today" with every other level after them. "New code" locks out the old code.
- **Sharing inside the class.** After a run, a child can press "Share with the class" (and share a level from the editor). Classmates see it under "Our class" only after the teacher says yes; a child can ask the teacher to look at a share, which hides it until then. "On the projector" shows a shared program big.
- **The class's own levels.** Add levels from the level editor on the teacher's screen ("My levels" in this browser, or the level and solution files), or with `codezoo class add-level CLASS LEVEL.json`. They are checked like `levels validate` first, then can be picked for today.
- **Progress to and from home.** "Take my progress home" saves a child's progress to a file; at home it loads in the Grown-ups area ("Load a player from a file") or with `codezoo profile import`. "Bring my progress from home" does the reverse in a workshop. "Save the whole class to a file" (or `codezoo class export`) keeps every player.

## Offline browser version

```bash
uv run codezoo build-web site/
```

Writes a static site to `site/`: the same web client, with the engine running in the browser (Pyodide 0.29.5, Python 3.13, in a web worker) instead of `codezoo serve`. A service worker keeps every file, and Pyodide after its first load, so it then works with no network; players' progress lives in the browser (IndexedDB). Put the folder on any static host (GitHub Pages, Cloudflare Pages), or try it with `python -m http.server --directory site`. `--pyodide URL` loads Pyodide from somewhere else (for example a copy next to the page). Release islands newer than Pyodide's Python show as locked there.

## Pilots and accessibility

Everything for running a pilot with children is in [docs/pilot/](docs/pilot/README.md): parent letter and consent form (English, Slovak), facilitator guide, observation sheet, device checklist and the teacher app guide.

- **Pilot recording is opt-in.** A grown-up ticks "Take part in a pilot" in the Grown-ups area (or the teacher on the teacher's screen, or `codezoo parent set --pilot`). Only then does CodeZoo record, on this computer, what the pilot metrics need, and never in private mode. Players of modules 1–5 get 3 short questions before and after the module (the same ones, to measure learning; never scored in front of them), and once a day a "Would you like to play again?" smiley row after a solved level.
- **Export with consent.** "Export pilot data" lists what the file holds and saves it only after "I agree": a random pilot id and an age band per player, tries, stars and hints per level, right answers before and after, minutes to the first star, errors and smileys. No names, pictures, programs or typed text, and nothing is ever sent. `codezoo pilot report FILES...` merges the files into the pilot metrics with their targets.
- **Device check.** `check.html` tests a device in about 10 seconds: engine start, a level run, the 3D stage's frame rate, storage, and the hub. It offers the 2D stage when 3D is slow.
- **Look and feel.** The "Aa" button: colours (as the device, light or dark; the ☀️/🌙 button next to it switches them too), text size, easy-to-read text, high contrast, less motion, and big targets (bigger blocks and buttons; tap a palette block to add it to the end of the program). A screen reader hears the world described in words, and results, hints and errors as they happen. Blocks can be used with the keyboard (Blockly 13's built-in keyboard navigation).
- **No installing.** Families: `codezoo build-web site/ --pyodide-dir node_modules/pyodide` puts Pyodide inside the site, so it loads nothing from a CDN; the "Pilot builds" workflow publishes it on GitHub Pages once Pages is on and the repository variable `CODEZOO_PAGES` is `true`. Teachers: `CodeZoo-Teacher.exe` (from the same workflow, or `scripts/build_teacher_app.py`) runs `codezoo teacher`, which asks for the class and starts the hub; it is not code-signed yet.

## Cub mode (ages 6–8) and read aloud

For children who can't read yet. A grown-up turns it on per player: "Cub mode" when adding a player, the switch in the Grown-ups area, the teacher's screen (per child, or "New players start in Cub mode" for the class), or `codezoo profile add NAME --cub` / `codezoo profile cub NAME --on|--off`.

- **Its own levels.** Two modules of 10: steps and turns, then repeat. Each follows *predict, fix, make*: watch a ready program after tapping the square where you think the animal stops; fix a program with one wrong block; build your own. Big numbered buttons replace the level list.
- **Picture blocks.** 👣 step, ↺ ↻ turn, ✋ grab, 🔁 repeat: the same blocks and the same Python underneath. A tap on a palette block adds it to the program.
- **Colour-linked code.** Each block's code lines are tinted in its colour, with a bar pattern of its own (colour is never the only signal); new lines glow, and tapping a line makes its block glow and reads it aloud.
- **Read aloud.** Goals, hints, results, feelings and tapped blocks, with the device's own speech voices (nothing is recorded or sent). Always on in Cub mode (with a mute button); for everyone else it's "Read aloud" in Look and feel. Without a voice for the language nothing is read, and Look and feel says so.
- **Moving on.** When every cub level is solved, the Grown-ups area asks "Ready for the main course?". Nothing is said to the child, and there is no age rule.

## Make a game (game mode, first step)

The program writes the rules of a world, then you play it live with the arrow keys or the on-screen buttons. Start the local web UI:

```bash
uv run codezoo serve --open
```

Then click "Make a game" in the top bar, or open the game page directly:

```text
http://localhost:8765/game.html
```

Pick a game (`?game=collect-guard` in the address opens one), change its code, press ▶ Play, and play with the arrow keys; Stop ends the game, "Start code again" brings back the game's own code. On a classroom hub (`codezoo class serve`) children open "Make a game" the same way, and the teacher's "Pause everyone" pauses games too. In the offline build (`codezoo build-web site/`) it is `site/game.html`.

The program runs once to set up; then the game calls its handlers on every tick: `on_key(key)`, `on_tick()`, `on_item(item)` and `on_touch(critter)`. Critters are your own classes built on `Critter` (`class Guard(Critter)` with an `on_tick(self)` that uses `self.step()`, `self.turn_around()`, `self.wall_ahead()`). Programs also get `score.add(1)`, `win()`, `lose()`, `go("left")`, `where()`, `ticks()` and `critters()`. Bumps don't crash a game, and a loop that runs forever ends it with a kind message instead of freezing it. Games are JSON files in `mse_codezoo/content/games/`; the first one is "Bananas and the guard". Your changes to a game's code stay in this browser. Play on the 3D stage (the zoo's animals, a crocodile guard, ghosts and beetles as critters) or the flat 2D board; the switch above the stage is remembered in this browser, and devices without WebGL use 2D. It works on a classroom hub and in the offline build too.

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

## Commands

`codezoo --help` lists the commands in the same groups as below; `codezoo COMMAND --help` shows each one's options. Every command takes `--lang en|sk` before its name (`codezoo --lang sk check ...`, or set `CODEZOO_LANG`).

`LEVEL` is a level id (`m01-l01`) or a path to a level `.json` file. A program may `import` helper files that sit next to it (your own `tricks.py`), and the files a level brings with it.

### Play and learn

- `codezoo play`: Terminal game: edit a `.py` file, run it, watch the grid. `--level ID`, `--profile NAME`, `--dir PATH`, `--speed 1-5`, `--no-color`. Main course only; Cub mode is in the browser
- `codezoo serve`: Local web UI with stage, blocks and code; game mode is at `/game.html` ("Make a game"). `--port 8765`, `--open`, `--data-dir PATH`
- `codezoo run LEVEL PROGRAM`: Runs a program in a level. `--trace` shows every step and the grid, `--json`, `--animal NAME`, `--save RUN.json` keeps the run for `replay` and `story export`
- `codezoo check LEVEL PROGRAM`: Goal, stars and a hint; exit code 0 only when solved. `--animal NAME`, `--profile NAME` saves the result
- `codezoo replay RUN`: Replays a saved run on the terminal grid. `--speed 1-5`, `--no-color`

`run` and `check` also take `--python 3.11`…`3.15` to run a program as written for that Python release.

### Print and share

- `codezoo story export RUN`: A printable storybook of a saved run. `-o story.html`
- `codezoo cards print`: Printable unplugged cards with word codes and QR codes. `--animal NAME`, `-o cards.html`
- `codezoo cards unlock CODE`: Unlocks a card's sticker. `--profile NAME`
- `codezoo graduate PROGRAM`: A plain `.py` that runs in normal Python: the zoo's commands become stand-ins that print. `-o OUT.py`, `--run`

### At home (grown-ups)

- `codezoo profile list`: Players on this computer, with their stars (and Cub mode)
- `codezoo profile add NAME`: Adds a player. `--picture fox`; `--cub` starts them in Cub mode (ages 6–8)
- `codezoo profile cub NAME`: Cub mode on or off for a player. `--on` / `--off`
- `codezoo profile export NAME`: Saves a player's progress to a file, for another computer. `-o FILE`
- `codezoo profile import FILE`: Loads a player from such a file, also one brought home from a class
- `codezoo profile remove NAME`: Removes a player and their progress. `--yes`
- `codezoo parent show`: The grown-up settings
- `codezoo parent set`: `--daily-minutes N` (0 = no limit), `--private/--no-private`, `--pilot/--no-pilot`
- `codezoo parent pin`: Sets or changes the grown-up PIN; `--clear` removes it
- `codezoo parent report NAME`: What a player has learned so far

When a PIN is set, `profile cub`, `profile remove`, `parent set`, `parent pin`, `parent report` and `pilot export` ask for it.

### In the classroom

- `codezoo teacher`: Asks which class to open (or makes one) and starts the hub: what the teacher app runs. `--port 8765`
- `codezoo class new NAME`: A workshop or a class. `--type workshop|class` sets the defaults; `--names/--no-names`, `--roster/--no-roster`, `--delete-at-end/--keep`, `--class-lang en|sk` (the language children's devices open in)
- `codezoo class serve NAME`: Runs the classroom hub on the local network and opens the teacher's screen. `--host 0.0.0.0`, `--port 8765`, `--open/--no-open`
- `codezoo class list`: Classes and workshops on this computer
- `codezoo class add-player NAME PLAYER`: Adds a player to a class's list. `--picture cat`, `--cub`
- `codezoo class add-level NAME LEVEL`: Adds your own level (from the level editor) to a class. `--solution FILE`
- `codezoo class export NAME`: Saves the whole class to one file. `-o FILE`
- `codezoo class delete NAME`: Deletes a class and all its players' progress. `--yes`
- `codezoo pilot export`: This computer's pilot data, anonymised (recording is on with `parent set --pilot`). `-o FILE`
- `codezoo pilot report FILES...`: Merges pilot exports into the pilot metrics with their targets. `-o report.md`

`codezoo class --data-dir PATH ...` keeps the classes somewhere other than the user-data folder.

### Make content

- `codezoo levels list`: Bundled levels
- `codezoo levels show LEVEL`: One level: goal, star rules, blocks, grid and hints. `--animal NAME`; `--solution` adds the reference solution
- `codezoo levels validate`: Checks level files and that each reference solution earns every star (islands newer than this Python are skipped). `--all` or `PATHS...`
- `codezoo world new ANIMAL`: Scaffolds `SPEC.md`, `pack.json` and a first level for a new animal. `--content DIR`
- `codezoo blocks PROGRAM`: Block outline with each block's lines and node id

### For developers

- `codezoo schema`: JSON Schema of the program model (IR), the contract with the web client. `-o FILE`
- `codezoo build-web OUT`: The offline browser version as static files. `--pyodide URL`; `--pyodide-dir DIR` copies Pyodide into the site

## Supported Python (phase 4)

Phase 2: calls, variables, `=` and `+=`-style updates, `for` and `while` loops, `if`/`elif`/`else`, comparisons (also chained, `is`, `in`), `and`/`or`/`not`, `x if c else y`, `+ - * / // % **`, numbers, text, `True`/`False`/`None`, f-strings (with `!r` and format specs), indexing and slicing, text methods, comments and `pass`.

Phase 3: `break`/`continue`; `def` with defaults and keyword arguments, `return`, `global`, closures, `import` of helper files, recursion (40 deep); `try`/`except`/`else`/`finally`, `raise`, `assert` with real Python exceptions; lists, tuples, dicts, sets, unpacking, `del`, comprehensions and their methods and builtins.

Phase 4 adds:

- **Comprehensions and generators:** `lambda`, `map`, `filter`, `iter`, `next`, `StopIteration`, generator functions with `yield` (paused and resumed on each `next()`, `.send()`, `yield from` with return values), generator expressions, endless generators and pipelines. Lazy iterators count what they hand out, so an endless one stops at the zoo's limit.
- **Objects:** classes with class and instance attributes, `__init__`, methods, `@property` (and setters), `@classmethod`, `@staticmethod`, inheritance, `super()`, multiple inheritance and `__mro__`, special methods (`__str__`, `__repr__`, `__eq__`, `__lt__`, `__len__`, `__call__`, `__iter__`, `__enter__`/`__exit__`...), your own exceptions, `@dataclass` (defaults, `field()`, `frozen`, `order`, `__post_init__`, `asdict`) and `NamedTuple`. Classes can't define hooks into the interpreter (`__getattribute__`, `__del__`...), and `__class__` and friends stay hidden.
- **Decorators:** functions as values, `*args`/`**kwargs` (in definitions and calls), `nonlocal`, hand-made and stacked decorators, decorators with arguments, class-based decorators, `functools.wraps`, `functools.cache`/`lru_cache`, `reduce`, `partial`.
- **Concurrency:** `async def`, `await`, `asyncio.run`, `sleep`, `create_task`, `gather`, `Lock` (`async with`), `Queue`, `TaskGroup` and `except*`; `threading.Thread`, `Lock` (`with lock:`). Everything runs on a simulated clock, tasks in CPython's own order and threads statement by statement with a seeded scheduler (with or without the GIL), so a race happens the same way every run.
- **First project:** `input()` (answers come from the level), `open()` with `read`/`readline`/`write`, iterating lines, `with` (also several in brackets), `if __name__ == "__main__":`, and the modules `math`, `random` (seeded), `json`, `string`, `time`, `itertools`, `copy`, `dataclasses`, `typing`, `__future__`.
- **Baseline 3.10/3.11:** `match`/`case` (literals, captures, sequences with `*rest`, mappings, classes, `|`, guards, `as`), `X | Y` in `isinstance`, `zip(strict=True)`, exception groups.
- **Release islands:** 3.12 nested f-string quotes, `type` aliases and `[T]` type parameters, `itertools.batched`; 3.13 `copy.replace` and free threading; 3.14 template strings `t"..."` and `except A, B:`; 3.15 `frozendict`, `sentinel`, `[*x for x in xs]` and `lazy import`. Type hints are kept as written and never run (like 3.14's deferred annotations).

Not supported (kept as raw code with a note): `async for`, async generators, `:=`, `raise ... from`, `a = b = ...`, calling a call (`f()()`), `/` in inputs.

## Levels

186 levels: two Cub mode modules (Steps and turns, Repeat; 10 each), and 166 in fifteen modules and five release islands: 1 Sequences (12), 2 Loops (11), 3 Variables (11), 4 Types and text (12), 5 Conditions (11), 6 Loops II (11), 7 Functions (12), 8 Errors and debugging (9), 9 Collections (10), 10 Recursion (10), 11 Comprehensions and generators (9), 12 Objects (9), 13 Decorators (8), 14 Concurrency (8), 15 First real project (6), and the islands baseline 3.10/3.11 (5), 3.12 (3), 3.13 (2), 3.14 (3), 3.15 (4). Every module has debugging levels whose starter program has a bug to fix. Signature levels belong to one animal; all other levels can be played by every animal, and `codezoo levels validate --all` checks every reference solution for every animal that can play it. Goals can ask the animal to collect items, avoid some, reach a square, say exact text, build a dam, print lines, leave text in a file, or be done by a tick of the clock. Every level has a Slovak title and hints.

## Third-party software

| Component | Version | Licence | Where |
| --- | --- | --- | --- |
| [Blockly](https://github.com/RaspberryPiFoundation/blockly) | 13.3.0 | Apache-2.0 | `mse_codezoo/web/vendor/blockly/` (unchanged copy, see its README and LICENSE) |
| [three.js](https://threejs.org/) | 0.170.0 (r170) | MIT | `mse_codezoo/web/vendor/three/` (unchanged copy, see its README and LICENSE) |
| [Pyodide](https://pyodide.org/) | 0.29.5 | MPL-2.0 | not bundled: the offline build loads it from jsDelivr (or `--pyodide URL`) |

CodeZoo's own code is licensed under the Apache License 2.0 (see `LICENSE` and `NOTICE`); vendored components keep their own licences. Code shared earlier under the MIT licence stays available under MIT.
