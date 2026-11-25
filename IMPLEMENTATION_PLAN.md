# CodeZoo – Implementation Plan

Nov 1, 2026 · @Michal · revised Nov 19, 2026: engine becomes a uv Python package (`mse_codezoo`, flat layout) with a click CLI; parent, profile and story ideas taken from the Applaydu comparison · Nov 20, 2026: phase 4 built (see Phase 4 steps)

## Vision and concept

CodeZoo (working name) teaches real programming through small games: the learner picks an animal, and that animal's world supplies the puzzles, from moving one step to running a colony in parallel. Like CodeMonkey, every level is a tiny goal on a visual stage that the learner solves by writing a program; unlike it, every solution is shown at once as blocks, as real code and as animation.

**Core principles**

- **Animal = theme, not curriculum.** All animals cover the same concept ladder; the animal changes the story and sprites and adds one or two tricks of its own (see [Shared core, animal tricks](#shared-core-animal-tricks)). A learner who switches animal keeps their progress.
- **Blocks and code are the same program.** Dragging a block writes code; typing code rebuilds blocks. Learners graduate from blocks to text at their own pace.
- **Python first, language-neutral inside.** Programs are stored in a neutral form and printed as Python. Adding JavaScript, Lua or another language later means adding a printer and a runtime, not rewriting levels.
- **One Python engine, thin clients.** The learning engine (program model, parser, interpreter, world, goal checker, levels, profiles) is one pure-Python package, `mse_codezoo`, managed with uv and driven by a click CLI (`codezoo`). The terminal, a local web UI and later an offline browser build are all clients of that same engine, so a level behaves identically everywhere and is tested with plain pytest.
- **Calm and safe by design.** No ads, no purchases, no account needed, works offline. A grown-up area holds profiles, daily time limits and a concept report (see [Parents, profiles and safety](#parents-profiles-and-safety)).

**Animal worlds (first set)**

| Animal | World | Mechanic that fits the concepts |
| --- | --- | --- |
| Monkey | Jungle | Walk, turn, grab bananas: sequences, loops |
| Penguin | Ice field | Slide until blocked, count fish: variables, conditions |
| Beaver | River | Build dams from logs of types and sizes: types, lists, comprehensions |
| Fox | Forest | Sneak past guards with rules: conditions, functions, decorators as "tricks" |
| Octopus | Reef | Eight arms act at once: parallelism, concurrency |
| Bee | Hive | Queen, workers and drones as classes: object-oriented programming |

### Shared core, animal tricks

Every world uses the same core actions on the same grid: `step`, `turn_left` / `turn_right`, `grab` / `drop`, sensors (`is_blocked()`, `item_here()`, `item_ahead()`) and `say()`. Animal packs only rename them (`grab` → `catch()` for the penguin). On top, each animal adds one or two tricks that only make sense in its world:

| Animal | Tricks | Modules that use them |
| --- | --- | --- |
| Monkey | `climb()` a tree, `swing()` across a gap | Functions, Loops II |
| Penguin | `slide()` until blocked | Conditions, Loops II, Errors |
| Beaver | `build(log)`; logs carry a type and a length | Types and text, Collections, Comprehensions |
| Fox | `sniff()` returns a footprint, `hide()` | Conditions, Recursion, Decorators |
| Octopus | Eight `arm` tasks that act at once | Concurrency |
| Bee | Queen, worker and drone objects | Objects |

That gives two kinds of level:

- **Core levels** use only core actions. They are written once and re-skinned for every animal, so a learner can switch animals and keep going. About 8 of a module's 12 levels.
- **Signature levels** use one animal's tricks and exist only in that world; they are where the module's concept shows best. About 4 per module, from the animal that suits the concept.

Progress is tracked per concept, not per animal; other animals' signature levels stay open as bonus levels.

**Audience:** learners aged 6 and up (Cub mode for ages 6–8) and adult beginners; teachers get a class view in a later phase. **The MVP is built for children aged 8–12** at home or in after-school clubs; Cub mode, adults and teachers follow once it works for them.

## Competitors and positioning

The closest products teach code through goal-driven games; none shows blocks, real Python and animation as one program from the first level while staying free, offline and account-free.

| Product | What it does | Where CodeZoo differs |
| --- | --- | --- |
| CodeMonkey | Game levels solved with code; blocks for young children, then CoffeeScript or Python; school licences | Blocks, real Python and animation always side by side; free, offline, no account |
| CodeCombat | Typed Python or JavaScript in a fantasy RPG; free start, paid content and school licences | Blocks and code are one program; Cub mode from age 6; ladder reaches concurrency and new Python releases |
| Scratch / ScratchJr | Free, open-ended block programming with a huge community | Real Python text from day one; goal-driven levels with structure checks |
| Code.org | Free school courses; blocks with a JavaScript text view in some tools | Python; works offline at home; parent area with limits |
| Blockly Games | Free short block puzzles that end in JavaScript | Full Python ladder, animal worlds, progress and parent report |
| Tynker | Paid block-to-Python and JavaScript courses and games | Free, no account, release islands |

**Positioning:** the free, offline game where a child's blocks *are* real Python from the first level, and the same course grows to classes, recursion and concurrency.

Competitor details are from general knowledge as of late 2026; check each product's current offer before using this table publicly.

## Learning curriculum

The course is 14 modules of about 12 levels each, ordered so every concept is needed by the next; each module ends in a "boss level" that combines everything so far. Example levels use the monkey unless another animal suits the concept better; core levels are re-skinned for every animal, signature levels belong to one. Modules 13–14 are optional advanced modules, recommended from age 13. Module 15 is an optional graduation project that runs in real Python. Coverage was checked against the "Learn X in Y minutes" Python 3 reference and notes on generators, decorators and data classes (dataclass, NamedTuple, attrs, pydantic): every topic there has a home in one of the 15 modules.

| # | Module | Concepts | Example game level |
| --- | --- | --- | --- |
| 1 | Sequences | Commands, order, comments, `say()` / `print()` | Monkey: `step(3)`, `turn_left()`, `grab()` to reach one banana, then `say("Yum!")` |
| 2 | Loops I | `for` with `range`, repetition | Collect 10 bananas in a row with a 3-line loop instead of 30 lines |
| 3 | Variables | Naming, assignment, updating | Penguin: `fish = fish + 1`; keep score while sliding |
| 4 | Types and text | `int`, `float`, `str`, `bool`, `type()`, conversion, powers `**`, string methods, indexing and slicing text, f-strings, `.format()` (old `%` formatting shown, not practised), `print(..., end="")` | Beaver: logs labelled `"oak"`, `2.5` m, `True` (wet); sort by type and print a label `f"{kind}: {length} m"` |
| 5 | Conditions | `if`/`elif`/`else`, comparison, chained `1 < x < 3`, `and`/`or`/`not`, truthiness (`0`, `""`, `None` count as false), `is` vs `==`, `is None`, `x if c else y` | Penguin: slide only `if ice_ahead`; avoid cracked ice |
| 6 | Loops II | `while`, `break`, `continue`, nested loops | Monkey: `while not at_tree(): step(1)`; spiral jungle maze |
| 7 | Functions | `def`, parameters, default and keyword arguments, return values (several at once), scope, `global`, importing your own helper file | Teach the monkey `climb_tree(height)`, keep it in `tricks.py` and `import` it in 5 levels |
| 8 | Errors and debugging | Reading tracebacks, `try` / `except` / `else` / `finally`, `raise`, `assert` | Penguin: thin ice raises `CrackError`; catch it and slide around. Bug-hunt levels start from a broken program |
| 9 | Collections | `list` (`append`, `pop`, `insert`, `remove`, `index`, `extend`, `del`), slicing, `tuple`, unpacking and swapping `a, b = b, a`, `a, *rest = ...`, `dict` (`get`, `setdefault`, `update`, `**` merge), `set` and `& \| - ^`, `in`, iteration | Beaver: inventory `{"oak": 3, "pine": 2}`; build a dam needing exact counts |
| 10 | Recursion | Base case, recursive case, the call stack | Fox: `explore(tunnel)` calls itself for each side tunnel and stops at dead ends; the stage draws the call stack as nested burrows |
| 11 | Comprehensions and generators | list/dict/set comprehensions, filtering, `lambda`, `map`, `filter`, iterators (`iter`, `next`, `StopIteration`), generators with `yield` (paused and resumed on each `next()`), generator expressions `( )` vs. list comprehensions `[ ]` (memory vs. speed), infinite generators, generator pipelines | Beaver: `[log for log in river if log.length > 2]` replaces a 5-line loop. Bee: `def honey():` `yield`s one drop each time the jar asks, so a huge field never fills memory; a pipeline `flowers()` → `nectar()` → `honey()` passes one drop at a time, and the stage shows each stage pausing until asked |
| 12 | Objects (OOP) | classes, class and instance attributes, `__init__`, methods, `@property`, `@classmethod`, `@staticmethod`, inheritance, `super()`, polymorphism; data classes with type hints (`@dataclass`, defaults and `field()`, `frozen=True`, `order=True`, `__post_init__`, `slots=True`, `asdict`), `NamedTuple`; multiple inheritance and the MRO as an advanced level | Bee: `class Worker(Bee)`; queen sends any bee `.work()` and each does its job |
| 13 | Decorators (advanced, optional) | functions as values and references, closures, `*args` / `**kwargs`, hand-made decorators then `@decorator`, stacking decorators (order matters), decorators with arguments (`@times(3)`), decorating methods, class-based decorators (`__call__`), `functools.wraps`, everyday uses: timing, logging, caching with `functools.cache` | Fox: `@sneaky` wraps any move so guards don't hear it; `@times(3)` repeats |
| 14 | Parallelism and concurrency (advanced, optional) | threads vs async, `async`/`await`, races, locks, queues | Octopus: 8 arms gather shells at once; two arms grab one shell = race, fix with a lock |
| 15 | First real project (graduation, optional) | `input()`, files with `with open(...)`, standard modules (`math`, `random`), `if __name__ == "__main__":`, running a `.py` file in normal Python, adding a third-party package with uv (for example `pydantic` to validate the quiz's saved data, compared with a `@dataclass`; `attrs` mentioned as the older alternative) | Zoo keeper's quiz: a program that asks questions with `input()`, keeps a high-score file and uses `random`; exported as a real `.py` and run in CPython |

**How each level teaches**

1. **Goal** shown on the stage ("collect all bananas in ≤ 5 lines").
2. **Starter program** in blocks or code, sometimes deliberately broken (2–3 debugging levels in every module, so debugging is practised throughout, not only in module 8).
3. **Run and watch**: the animal acts out the program step by step; the current block and code line glow.
4. **Stars** for solving, staying under the line budget, and using the target concept (checked on the program's structure, not just the result).
5. **Hint ladder**: nudge → concept card → partial solution.

**Concurrency made visible.** Module 14 shows each thread or task as its own coloured lane under the stage, with a timeline scrubber, so learners see interleaving, waiting on `await`, and why a lock stops two arms grabbing the same shell. Real CPU parallelism is simulated by the stepper scheduler so results are repeatable.

## Python versions and release islands

The core course targets Python 3.11 syntax, and every newer release (3.12 to 3.15 today) gets its own "release island": a short side quest of 3–5 levels that teaches what that version added. Learners pick a version in settings; the editor accepts only syntax available in that version and says which release introduced anything newer.

Why 3.11: Python 3.10 reached end of life in October 2026, when 3.15.0 shipped on October 9 ([Python blog](https://blog.python.org/2026/10/python-3150-final-is-here/), [versions](https://www.python.org/doc/versions/)), so 3.11 is now the oldest supported release. The baseline still includes 3.10's `match`, and adds exception groups and `asyncio.TaskGroup`, which module 14 can use directly.

| Version | Feature | Concept | Game level |
| --- | --- | --- | --- |
| Baseline (since 3.10) | `match` / `case` pattern matching | Branching on shape of data | Fox: `match footprint:` — `case ("paw", size)` hide, `case ("boot", _)` run, `case _` keep sniffing |
| Baseline (since 3.10) | `X \| Y` union types in hints | Types that can be one of two | Beaver: `def weigh(log: int \| float)`; scale rejects a `str` log |
| Baseline (since 3.10) | `zip(..., strict=True)` | Pairing lists safely | Penguin: pair chicks with fish; uneven lists raise an error instead of a hungry chick |
| Baseline (since 3.10) | Parenthesized context managers | `with` and cleanup | Monkey: `with (basket, ladder):` both are put back after the harvest |
| Baseline (3.11) | Exception groups, `except*` | Several errors at once | Bee: three workers fail differently; `except* RainError` and `except* WaspError` handle each group |
| Baseline (3.11) | `asyncio.TaskGroup` | Structured concurrency | Octopus: arms start in a task group; if one arm is stung, all arms retract safely |
| Baseline (3.11) | Error locations with `^^^` markers | Reading tracebacks | Debug quest: find the exact broken part of a long expression from the caret marks |
| 3.12 | f-string upgrade (PEP 701): nested quotes, any expression | Formatting text | Monkey signboard: `f"{name + "'s"} bananas: {count}"` |
| 3.12 | Type parameter syntax `def first[T](items: list[T])`, `type` statement | Generics | Beaver: one `Stack[T]` class stores logs, stones or fish |
| 3.12 | `itertools.batched` | Chunking data | Bee: pack 23 honey drops into jars of 6 |
| 3.13 | Free-threaded build (no GIL, experimental) | True parallel threads | Octopus: same shell-gathering level run with and without the GIL; lanes show real overlap vs. turn-taking |
| 3.13 | New colourful REPL, better error hints | Exploring interactively | Sandbox "pond": type one line at a time and see the penguin react |
| 3.13 | `copy.replace()` | Immutable updates | Fox: make a copy of a guard's route with one change, original stays intact |
| 3.14 | Template strings, `t"..."` (PEP 750) | Safe text building | Bee: dance messages built with `t"..."`; a filter blocks a sneaky wasp inserting fake directions |
| 3.14 | Free-threading officially supported (PEP 779) | Parallel threads, production-ready | Octopus boss level: 8 arms, real threads, a lock-free counter vs. a locked one |
| 3.14 | `concurrent.interpreters` (PEP 734) | Isolated workers | Several separate reefs, each its own interpreter, sending shells through a queue |
| 3.14 | `except A, B:` without brackets (PEP 758) | Cleaner syntax | Quick refactor quest: tidy old handlers |
| 3.14 | Deferred annotations (PEP 649) | Forward references | Bee: `class Queen` refers to `Worker` defined later, no quotes needed |
| 3.15 | `frozendict` built-in (PEP 814) | Immutable mappings | Beaver: the dam blueprint is a `frozendict`; trying to change it is caught |
| 3.15 | Unpacking in comprehensions (PEP 798) | Flattening data | Bee: `[*cell for cell in combs]` collects all honey in one line |
| 3.15 | `sentinel` built-in (PEP 661) | "No value" vs. `None` | Penguin: `MISSING` fish vs. a fish whose weight is `None` |
| 3.15 | Explicit lazy imports (PEP 810) | Imports and start-up time | Monkey: `lazy import map` — the map is unpacked only when first opened, and the stage shows the faster start |
| 3.15 | UTF-8 by default (PEP 686) | Text encoding | Animals' names in many languages (š, ä, 中) saved and loaded without errors |

**How it fits the plan**

- **Model:** every IR node and builtin carries `since: "3.11"`; the Python adapter gets a `version` setting and refuses or explains newer syntax. Parsing uses CPython's own `ast` module, with `ast.parse(..., feature_version=(3, N))` as a first filter and our `since` table as the real gate (CPython documents `feature_version` as best-effort), so the message can name the release that introduced a construct.
- **Host Python:** syntax from a release can only be parsed by a host interpreter at least that new. Develop on the newest release (`uv python pin 3.15`); the package itself supports `requires-python = ">=3.11"`, and an island newer than the host shows as locked with a short explanation.
- **Levels:** level JSON gets `"minPython": "3.12"`; release islands unlock after the module whose concept they extend (e.g. the 3.13 free-threading levels after module 14).
- **Runtime:** the GIL vs. free-threading levels are simulated by the scheduler (one lane at a time vs. true overlap), so they behave the same in every browser.
- **Yearly cycle:** each October, when a new Python ships, add one island: read "What's new", pick 3–5 learner-visible features, build levels during the beta (May–September), publish with the final release.
- **Roadmap:** 3.11 baseline features go into core modules in phases 0–4; release islands 3.12–3.15 are a phase 4 content track (about 4 weeks for one level designer).

## User experience

The main screen has three synchronized panes — Stage, Blocks, Code — over one shared program, so a change in any pane appears in the others: blocks move instantly under the finger, and the code pane follows within about 100 ms, once the engine has printed the new program.

| Pane | What the learner does | Behaviour |
| --- | --- | --- |
| Stage (top or left) | Watches the animal act out the program | three.js low-poly 3D grid world; play, pause, step, speed slider, reset; concurrency lanes in module 14 |
| Blocks (bottom-left) | Drags Scratch-like blocks from a palette | Palette shows only blocks unlocked so far; C-shaped blocks for loops, `if`, `def`, `class` |
| Code (bottom-right) | Reads or edits real Python | Syntax highlighting, line numbers, errors in kid-friendly words; read-only in early modules |
| Console (right) | Reads what `print()` writes and what the variables hold | Printed lines as the run plays; the Variables bar (the debugger, see "Debugger" under the phase steps) shows the file's variables, the running call's own, what the last step did, and step back / step on |

**Synchronization rules**

- Blocks → Code: every block edit regenerates the code text from the shared program.
- Code → Blocks: typing is parsed after a 300 ms pause; if it parses, blocks rebuild; if not, blocks stay at the last valid version and the error is underlined.
- Code the block palette cannot show (an advanced construct) appears as a grey "raw code" block that still runs.
- Hover or select a block and its code lines highlight, and the reverse.

**Modes per module:** blocks only (modules 1–2) → blocks with live code preview (3–6) → both editable (7–10) → code-first with blocks as an outline (11–14).

**Layout:** CSS grid with draggable splitters; on phones the panes become tabs (Stage / Blocks / Code). Touch drag and keyboard navigation for blocks; colour-blind-safe category colours.

**Terminal client.** `codezoo play` shows the same level in a terminal: the stage as a coloured character grid that animates step by step, the program as a `.py` file opened in the learner's editor, and the blocks as an indented outline. It is the first playable client (phase 1), the tool level designers and CI use, and a good fit for adult beginners; children use the web UI.

## Cub mode (ages 6–8)

Children who cannot read yet use the same three panes, but blocks are icons, everything is spoken, and the code pane teaches by colour: each block and the lines it creates share one colour, so a child watches real code grow as they build, long before they can read it.

&#91;embedded content: Cub mode mock-up · colour-linked blocks and code\]

The code stays visible from day one, so "blocks make code" is something a 6-year-old sees, not something explained later.

**Colour-linked code**

- **One colour per block family**, used on the block and on a bar plus light tint behind each code line it produces: motion, loops, actions, conditions, events.
- **Add a block** → its lines slide into the code pane and glow for about a second, with a soft sound. **Remove it** → the lines fade out.
- **Run** → the active block and its line pulse together while the animal moves, so colour, line and action connect.
- **Tap a line** → its block wiggles. **Tap a block** → the narrator reads it ("Step three times").
- **Colour-blind safe:** each family also has its own bar pattern (solid, striped, dotted) and block shape; colour is never the only signal.
- **Ghost icons:** each code line can end with a faint copy of its block icon; a setting fades them out as reading grows.
- **Mini-games on the code pane:** "How many lines did your program make?", "Tap the line that moves the monkey".

**What changes from the main course**

| Aspect | Cub mode (6–8) | Main course (9+) |
| --- | --- | --- |
| Reading | Icons + voice narration | Text labels on blocks |
| Concepts | Sequences, loops, cause-and-effect; simple conditions from about age 7 | Full ladder, modules 1–14 |
| Code pane | Visible, colour-linked, read-only | Editable from module 7 |
| Activities | Predict-then-run puzzles + free Story mode | Puzzles, projects, release islands |
| Rewards | Stars as feedback, stickers in a zoo album, stickers decorate the animal's habitat; no leaderboards, no timers | Stars, line budgets |
| Sessions | Suggested 10–15 minutes; a parent-set daily limit ends play at the next natural stopping point with a goodbye animation, never mid-run; no auto-play of the next level | Self-paced; optional limit |
| Feelings | The animal shows how it feels about the run (proud, puzzled, "oops!"); a bug is "help the confused penguin", never a failure | Kind error messages |
| Off-screen | Printable unplugged cards per animal (act out the monkey's path on the floor); each card's QR code unlocks the matching level or sticker | Optional |
| Story | Story mode runs become a printable picture storybook | Optional |
| Input | Tablet-first, large touch targets, drag or tap-to-place | Mouse, keyboard, touch |

**Level pattern for cubs (PRIMM, simplified)**

1. **Predict:** the animal shows a ready-made program; the child taps where they think it will end up.
2. **Run:** watch it; matching block and line pulse.
3. **Fix or change:** one block is wrong (bug hunt, framed as a game) or one block can be swapped.
4. **Make:** Story mode with the same blocks, no goal, just play.

**Grown-ups in the loop**

- Co-play prompts on screen for a parent or teacher ("Ask: what happens if we add one more step?").
- A simple grown-up view shows which ideas the child met (sequences, loops), not time-pressure metrics; it lives in the parent area described below.

**Implementation**

- No new runtime: Cub mode is a UI profile over the same program model. The block mapper gets an icon-only label set; the Python adapter's source map (node id ↔ line range) already gives the block-to-line links used for colouring.
- Narration: recorded audio per block and per language, with the browser's speech synthesis as fallback.
- Decide at the phase 1 gate whether Cub mode joins the MVP: if pilot families ask for it, build it in phase 2 for modules 1–2, otherwise in phase 3. Narration starts with the browser's speech synthesis; recorded voices only for English and Slovak at first.
- *Built in phase 7 (Nov 21, 2026), before that gate*, as a per-player option, so the first pilot can try it with younger children instead of deciding without it. See "Phase 7 steps" under [Risks, open questions and next steps](#risks-open-questions-and-next-steps).

Research basis: [ScratchJr (MIT)](https://news.mit.edu/2014/scratchjr-coding-kindergarten), [KIBO tangible coding](https://kinderlabrobotics.com/blog/robotics-in-early-learning-robotics-makes-coding-tangible-concreteand-screen-free/), [PRIMM](https://static.teachcomputing.org/pedagogy/QR11-PRIMM.pdf), [Four P's](https://www.media.mit.edu/posts/cultivating-creativity-during-the-coronavirus-crisis/), [rewards in Scratch](https://lcl.media.mit.edu/resources/readings/chapter3-gamification.pdf), [hybrid blocks/text](https://arxiv.org/abs/1906.03060v1).

## Architecture

Everything hangs on one language-neutral program model inside one pure-Python package: clients only edit or display the model, language adapters translate it to text, and an in-house interpreter runs it step by step to drive the world.

&#91;embedded content: architecture · 3 panes, 1 program model, runtime\]

Blocks and code are two views of the same tree; only the interpreter talks to the world engine, which turns program actions into events that each client animates (character grid in the terminal, three.js in the browser).

**Package and tooling**

- **uv project, flat layout:** the importable package `mse_codezoo/` and `tests/` sit at the repository root, no `src/` folder. Distribution name `mse-codezoo`, command `codezoo`, also runnable as `python -m mse_codezoo`.
- **Build backend `uv_build`** with `module-root = ""`, which is what makes the flat layout work (its default is `src/`). Levels, animal packs and web assets are package data inside `mse_codezoo/`, so they ship in the wheel.
- **One runtime dependency, `click`,** imported only by `cli.py`. Every engine module uses the standard library only, so the same wheel can later run in Pyodide in the browser without changes.
- **Dev dependencies** in a uv dependency group: `pytest`, `ruff`; `hypothesis` later for parser round-trips. Everything runs as `uv run pytest`, `uv run ruff check`, `uv run codezoo ...`.

```toml
[project]
name = "mse-codezoo"
version = "0.1.0"
description = "Learn real Python through animal coding games"
readme = "README.md"
requires-python = ">=3.11"
dependencies = ["click>=8.1"]

[project.scripts]
codezoo = "mse_codezoo.cli:main"

[dependency-groups]
dev = ["pytest>=8", "ruff"]

[build-system]
requires = ["uv_build"]          # keep the version bound that `uv init` writes
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "mse_codezoo"
module-root = ""
```

**Flat source layout.** One module per concern; a module becomes a subpackage only when it outgrows about 500 lines.

```
mse-codezoo/
  pyproject.toml  uv.lock  .python-version  README.md
  mse_codezoo/
    __init__.py       __version__
    __main__.py       python -m mse_codezoo
    cli.py            click group and commands (the only module importing click)
    ir.py             node dataclasses, stable ids, JSON (de)serialisation
    versions.py       `since` table, Python-version gating
    lang_python.py    ast -> IR, printer with source map, block labels
    interpreter.py    generator-based evaluator, builtins whitelist, step/recursion limits
    scheduler.py      seeded cooperative scheduler for thread/async lanes
    world.py          grid world, neutral actions, world events
    goals.py          world-state + program-structure checks, stars
    levels.py         load and validate level JSON and animal packs
    profiles.py       profiles, progress, parent settings, time limits, concept report
    story.py          run -> storybook pages
    cards.py          printable unplugged cards with unlock codes
    term.py           terminal stage renderer for `codezoo play`
    server.py         stdlib HTTP server behind `codezoo serve`
    content/
      levels/m01-sequences/l01.json, l01.solution.py, ...
      animals/monkey/pack.json, ...
    web/              index.html, *.js (ES modules), vendor/three.module.js
  tests/
    conftest.py
    test_ir.py  test_lang_python.py  test_interpreter.py  test_scheduler.py
    test_differential.py   our interpreter vs CPython on the same programs
    test_levels.py         every level's reference solution earns 3 stars
    test_cli.py            click CliRunner
```

**Program model (IR).** Python dataclasses serialised to a JSON tree of statements and expressions with stable node ids: `Call`, `Assign`, `If`, `For`, `While`, `FunctionDef`, `ClassDef`, `Return`, `Decorated`, `Async`/`Await`, `Comprehension`, `RawCode`, literals, names, operators. Every node keeps its id across edits, so a block, a code range and an executing step all point to the same node. The JSON form is the contract with the web client.

**Language adapter interface.** Each language implements four things:

```python
class LanguageAdapter(Protocol):
    def parse(self, text: str, version: tuple[int, int]) -> ParseResult: ...  # program + errors
    def print(self, program: Program) -> PrintResult: ...                     # text + source map (node id <-> line/col)
    def block_label(self, node: Node) -> str: ...                             # how a node reads as a block
    def supports(self, node: Node) -> bool: ...                               # e.g. no decorators in Lua
```

The Python adapter parses with CPython's `ast` module and converts the tree to IR, instead of a hand-written tokenizer and parser; this removes the biggest risk of the earlier plan, a parser that drifts from real Python. Unsupported constructs become `RawCode` nodes with a kid-friendly note. The printer stays our own, because it must produce stable formatting and a source map; round-trip tests check that `parse(print(p))` gives back `p`. JavaScript is the planned second adapter, which also proves the model is truly neutral.

**Runtime: own interpreter vs. running real Python**

| Option | Step-by-step animation | Deterministic concurrency | Safety | Verdict |
| --- | --- | --- | --- | --- |
| Own IR interpreter (Python generators) | Native: yields at every node | Yes, simulated scheduler | Only whitelisted builtins and world actions exist | Use for all levels |
| `exec()` learner code with `sys.settrace` | Possible | No | Learner code gets full Python (files, network) | Reject |
| CPython in a subprocess | No | No | Isolated | Only for differential tests and the "real Python" graduation sandbox |

The interpreter is a generator per task: each statement yields `Step(node_id, event)` so clients highlight the block and line and animate the world. A cooperative scheduler interleaves tasks for threads and `async` code with a fixed seed, so a race happens the same way every run. Limits on steps and recursion depth stop infinite loops with a friendly message. Learner code never reaches `exec` or `eval`.

**Clients**

| Client | Phase | How it uses the engine |
| --- | --- | --- |
| Terminal, `codezoo play` | 1 | Imports the engine directly; character-grid stage, program in a file |
| Local web UI, `codezoo serve` | 2 | Static HTML, CSS and ES modules plus vendored three.js in `mse_codezoo/web/`, still no framework; talks JSON to a stdlib HTTP server on `localhost`. The browser edits IR JSON and asks the engine to parse, print and run; it never parses Python itself |
| Offline browser build (PWA) | 4 | The same wheel loaded in Pyodide inside a web worker, cached by a service worker, hosted on static pages; reaches tablets and Chromebooks with nothing to install |

Pyodide adds several megabytes on first load, which the earlier plan used as a reason to reject it. Here it only hosts our engine (stepping and scheduling stay ours), it is cached after the first visit, and it is not needed until phase 4. CI imports the engine in Pyodide from phase 2 so no non-stdlib import sneaks in.

**Block editor: Blockly or our own**

| Option | For | Against |
| --- | --- | --- |
| Google Blockly (Apache 2.0) | Mature drag, snap, touch, keyboard navigation and accessibility work; custom blocks; can be vendored as plain files, no build step | Its own look and workspace model; colour-linked code and stable IR ids need a mapping layer; a larger download |
| Own SVG editor | Exactly our look; IR ids native; small | Months of work on drag-and-drop, touch, keyboard and screen readers |

Decision: a two-week spike in phase 1 builds the module 1–2 blocks in Blockly with a Blockly ↔ IR JSON mapper. Keep Blockly unless colour-linked code or Cub mode's icon blocks prove impossible with it. The no-framework rule is about the app shell; a vendored block library does not break it.

**Threat model for learner code.** A learner running their own code on their own device is low risk; the real risk is code written by someone else (shared levels, starter programs, community packs). The own interpreter stays the default because it also gives stepping and repeatable races. It also means a later "real Python" mode for older learners can run their *own* code in CPython (a subprocess locally, Pyodide in the browser) without a heavy sandbox, as long as shared content never runs there.

## Command-line interface

`codezoo` is a click group; each subcommand is a thin wrapper over engine functions, so everything the CLI does is also testable without it. Commands print plain text by default and JSON with `--json`, which is what CI and the web server use.

| Command | What it does | Phase |
| --- | --- | --- |
| `codezoo run LEVEL PROGRAM.py [--trace] [--json]` | Runs a program headless in a level; `--trace` prints every step | 0 |
| `codezoo check LEVEL PROGRAM.py` | Goal and structure checks, prints stars and hints | 0 |
| `codezoo levels list` / `validate [--all]` | Lists levels; validates JSON and runs every reference solution (the CI gate) | 0 |
| `codezoo blocks PROGRAM.py` | Prints the block outline and source map, for debugging sync | 0 |
| `codezoo schema [-o FILE]` | Prints the IR JSON Schema, the contract with the web client | 0 |
| `codezoo play [--level ID] [--animal NAME] [--profile NAME]` | Terminal game: animated grid, opens the program in `$EDITOR`, reruns on save | 1 |
| `codezoo profile add/list/remove/export/import` | On-device learner profiles | 1 |
| `codezoo parent show/set/pin/report` | Grown-up settings behind the PIN: daily limit, private mode, learning report | 1 |
| `codezoo serve [--port 8765] [--open]` | Starts the local web UI | 1 |
| `codezoo story export RUN` | Turns a saved run into a printable HTML storybook | 3 |
| `codezoo cards print --animal NAME` | Printable unplugged cards (HTML, print to PDF) with unlock codes | 3 |
| `codezoo world new ANIMAL` | Scaffolds `SPEC.md`, `pack.json` and a first level for a new animal world | 3 |
| `codezoo replay RUN` | Replays a saved run in the terminal | 3 |

## Data model and content format

Levels are plain JSON. Core levels are written once per concept and re-skinned per animal; only signature levels are animal-specific. 14 modules × (8 core + 4 signature) is about 170 levels to write, not one set per animal (about 1,000).

**Level file** (`mse_codezoo/content/levels/m02-loops/l03.json`, with its reference solution next to it as `l03.solution.py`)

```json
{
  "id": "m02-l03",
  "module": "loops-1",
  "concepts": ["for", "range"],
  "world": { "size": [10, 6], "tiles": "....B.B.B.\n..........", "start": [0, 0, "east"] },
  "goal": { "type": "collect_all", "item": "B" },
  "constraints": { "maxLines": 3, "mustUse": ["For"] },
  "unlockedBlocks": ["step", "turn_left", "turn_right", "grab", "for_range"],
  "starter": { "kind": "program", "body": [] },
  "hints": ["Count the bananas.", "A loop repeats the blocks inside it."],
  "mode": "blocks_with_preview"
}
```

**Animal pack** (`mse_codezoo/content/animals/penguin/pack.json`) maps neutral terms to the theme: item `B` → "fish", action `grab` → `catch()`, low-poly 3D models (glTF or built in code), sounds, story lines per module. Programs call theme names, the IR stores neutral actions, so one solution checker serves every animal.

**Goal checker** runs the learner's program in the world, then checks two things: the world state (all items collected, animal at the exit) and the program's structure from the IR (a `For` node exists, ≤ 3 lines). Each level ships with a reference solution that `codezoo levels validate --all` runs in CI to prove the level is solvable.

**Learner progress** is stored only on the device, one JSON file per profile in the OS user-data folder (a small stdlib helper picks `%APPDATA%`, `~/Library/Application Support` or `~/.local/share`); the offline browser build keeps the same JSON in IndexedDB. Per level: `{levelId, stars, bestProgram, attempts, timeSpent, conceptsMet, mistakes}`. Parent settings (gate, limits, privacy mode) sit in a separate file so a child's export never contains them. Export/import as a file for now; optional cloud sync and teacher accounts come in phase 5.

**Saved runs** (`*.run.json`: level id, program IR, seed, step events) are small and deterministic, so they replay exactly and feed the storybook and shareable replays.

**Built-in level editor** (prototype in phase 3 when content production starts, full version with sharing in phase 4): the same three panes plus a tile painter, so teachers and the community can create levels without touching JSON.

## Parents, profiles and safety

Ideas taken from [the Applaydu comparison](docs/research/applaydu_overview_comparison_parental_controls.md) (Applaydu, Khan Academy Kids, PBS KIDS Games, Duolingo ABC). All four are free, ad-free and purchase-free; Applaydu is the only one with built-in screen-time limits, and it pairs play with physical toys, stories and customisation. CodeZoo takes the parts that support learning and leaves out the toy-marketing tie-in.

| Idea | Seen in | CodeZoo version | Phase |
| --- | --- | --- | --- |
| Grown-up area behind a gate | Applaydu (PIN), Khan Kids and Duolingo ABC (math/reading gate) | Parent area behind a written grown-up question, plus an optional PIN; holds profiles, limits, report, settings and export. CLI: `codezoo parent` | 1 |
| Built-in daily time limits | Applaydu only; others rely on OS controls | Daily limit and session length per profile; when reached, the current run finishes, the animal says goodbye, the next start shows a friendly "see you tomorrow". Stored on the device, no server | 1 (CLI), 2 (UI) |
| Several child profiles | Applaydu, Khan Kids, Duolingo ABC | Picture login per profile on shared family and classroom devices, no accounts | 1 |
| Skill and progress report | Applaydu (skills, time), Khan Kids (curriculum dashboard), Duolingo ABC (mastered letters) | Concept report from the IR checks: met, practised, mastered per concept; repeated mistakes ("often forgets to turn"); one co-play prompt to try at home. Time is shown but not highlighted. Printable | 2 |
| No account, offline, no ads, no purchases | All four | The default; nothing is ever sold, including cosmetics | 0 |
| Zero-data option | PBS KIDS Games | "Private mode" setting keeps only stars and unlocks, no history, attempts or saved programs | 2 |
| Physical-to-digital unlocks | Applaydu toy and leaflet scanning | Printable unplugged cards (`codezoo cards print`) carry a QR code and a short word code; scanning (camera processed on the device, optional) or typing the code unlocks the matching level or sticker. Nothing to buy | 3 |
| Co-created storybook | Applaydu "Let's Story!" | Story mode turns a saved run into picture pages with narration generated from the IR ("The monkey stepped three times and found a banana"); child and parent add a title and a line per page; print or save offline (`codezoo story export`) | 3 |
| Avatar and room customisation | Applaydu | Dress up your animal and decorate its habitat with earned stickers; cosmetic only | 3 |
| Emotional learning | Applaydu (Emotiverse) | Animals react with feelings to runs; debugging is framed as helping a confused animal; growth-mindset messages, never shaming | 2 |
| Many languages | Applaydu (19 languages) | Interface, block labels and narration translatable from phase 1; English and Slovak first; Python keywords stay English | 1 |
| Adaptive path | Khan Academy Kids | Suggest an extra practice level after repeated mistakes on a concept; the child can still pick freely | 3 |
| Privacy certification | Applaydu (COPPA, kidSAFE) | Privacy review against GDPR (children) and COPPA, and apply for a kid-safety seal before public launch | Before launch |

## Roadmap

A usable MVP for children aged 8–12 ships in about 14 weeks; the full ladder up to concurrency follows by week 36, with a learner pilot gating each step. The earlier 12- and 30-week figures had no team behind them and assumed a smaller interpreter; these are sized for the team below.

&#91;embedded content: roadmap · 6 phases, 5 gates\]

**Team assumption.** Two developers (one on the engine, one on the web client), a level and content designer and a part-time artist from phase 2, and an education specialist for a few days around each pilot. With one developer, roughly double every phase.

| Phase | Weeks | Deliverable | Effort | Gate |
| --- | --- | --- | --- | --- |
| 0 Engine | 1–4 | uv package, IR, `ast` → IR, printer with source maps, interpreter (sequences, `for`, variables), grid world with core actions, `codezoo run --trace` as the developer's terminal view, `check`, `levels validate`, 5 levels, CI | 2 devs × 4 weeks | All reference solutions pass; round-trip and differential tests green |
| 1 Kid prototype | 5–8 | `codezoo serve`, three panes, Blockly spike with IR mapper, simple 2D stage, monkey modules 1–2, first parent gate and profiles | 2 devs × 4 weeks | 5–8 children aged 8–12 play 30 minutes unaided; no lost code; Blockly and Cub mode decisions made |
| 2 MVP | 9–14 | Monkey only, modules 1–5, three.js stage, feelings, English and Slovak, `codezoo play` for adults; Cub mode modules 1–2 only if the phase 1 gate says so | 2 devs + designer × 6 weeks | Pilot metrics below met → **MVP** |
| 3 Middle ladder | 15–24 | Modules 6–10; penguin, beaver and fox with their tricks; storybook, printable cards with unlocks, habitat stickers, adaptive suggestions, level editor prototype | 2 devs + designer + artist × 10 weeks | Learning-gain and drop-off targets still met |
| 4 Advanced and offline | 25–36 | Modules 11–15 (13–15 optional); octopus and bee; concurrency lanes, release islands 3.12–3.15, offline browser build on Pyodide, full level editor | Same team × 12 weeks | Runs offline on the cheapest target tablet and Chromebook |
| 5 Classes | Later (built Nov 21, 2026; gate open) | Classroom hub on the local network (no cloud), join with class code + picture, teacher class view, class-only sharing | One developer + coding agent | Privacy review passed; one real workshop or class run on the hub |
| 6 Pilot readiness | Built Nov 21, 2026; gate open | Families play without installing anything, teachers get a one-file hub app, concept checks before and after each module, pilot metrics recorded on the device and exported with consent, a pilot kit, accessibility basics | One developer + coding agent | The first pilot (5–8 children) runs with the kit and returns its metrics |
| 7 Cub mode and read aloud | Built Nov 21, 2026; gate open | Cub mode for ages 6–8 per player (picture blocks, colour-linked code, two cub modules in the predict–fix–make pattern), read aloud with the device's speech voices, a grown-up's "ready for the main course?" | One developer + coding agent | 3–5 children aged 6–8 play the cub modules with a grown-up nearby; read aloud works on the pilot devices in English and Slovak |
| 8 Game mode | G0 built Nov 24, 2026; G1–G3 built Nov 25, 2026 (gates open) | Children write the rules of a world (event handlers, critters, score) and play it live; playtest bot, templates, sharing, later classroom multiplayer. See [Future improvements, section 4](#4-game-mode-children-make-their-own-games) | One developer + coding agent | Steps G0–G3 have their own gates |

**The interpreter grows module by module.** Each phase adds only the constructs its modules need, each with its own differential tests: phase 0 calls, `for` and assignment; phase 2 `if`, `while` and strings; phase 3 functions, imports, exceptions, collections, recursion and comprehensions; phase 4 classes, decorators and `async`.

The hardest technical risk (blocks and code staying in sync over one model) sits in phases 0–1 on purpose: phase 0 proves the model with the printer and source maps, phase 1 with a live block editor in front of children, before content is produced at scale.

**Pilot metrics.** Starting targets for every gate from phase 1 on; revisit them after the first pilot.

| Metric | Target |
| --- | --- |
| Module completion | ≥ 70% of learners who start a module finish it |
| Time to first success | Median ≤ 5 minutes from opening level 1 to the first star |
| Solved before the last hint | ≥ 60% of levels solved before the partial-solution hint |
| Drop-off | No single level loses more than 15% of the learners who reach it |
| Learning gain | The post-module concept check beats the pre-check for at least 2 of 3 learners |
| Sync reliability | Zero lost learner code; fewer than 1 sync bug per 10 sessions |
| Enjoyment | At least 4 of 5 children want to play again (smiley scale); parents would recommend it |

The app records these on the device only; pilot families export them by hand, with consent.

## Lessons from vibe game development

As of October 2026, coding agents can build browser games that are genuinely fun, so CodeZoo uses them to prototype worlds and produce content fast, while the learning engine (program model, interpreter, goal checker) stays carefully hand-designed. Based on Simon Willison's [October inflection point for vibe game development](https://simonwillison.net/2026/Oct/28/vibe-game-development/) (Oct 28, 2026).

| What the post showed | How CodeZoo applies it |
| --- | --- |
| A small game (Tree Appreciator) came out of one chat prompt with no iteration | Prototype each animal world as a one-shot three.js game before engine work; keep only the mechanics that feel fun |
| Emberwick grew in steps: engine → world details → "turn this into an actual game" | Build each module in the same order: mechanic → world → story, with a playtest between steps |
| "Make it a LOT more fun" transformed Battle Drones | Every module's definition of done includes a "fun pass" prompt plus a playtest with real learners |
| Quarter Sun Cove started from a brainstorm turned into a SPEC.md, then a long agent run | Write a SPEC.md per animal world (characters, mechanic, concept mapping, level list) before an agent builds it |
| Asking the model to keep surprising and delighting the player produced many easter eggs | Add small surprises per world: animal reactions to good code, hidden collectibles, a "zoo album" like his herbarium |
| Most fixing went into story-state bugs (a character in the wrong place for a quest) | Extend the CI reference-solution runs to replay every level's story state, not just its goal |
| A level editor and a model gallery came almost for free | Prototype the level editor in phase 3, as soon as content production starts (not at the end); add an animal model gallery |
| LLMs played each other through a pause, read state, act loop; games had replays | "Rival" levels: the learner's program plays a bot program turn by turn on the stepper; every solution saved as a shareable replay |
| An open-source release was forked and re-themed within a day | Publish animal packs under an open licence so teachers and the community can re-skin worlds |
| Mobile web games on static hosting feel native | Confirms the phase 4 offline browser build; host on GitHub Pages or Cloudflare Pages |
| Many players reject AI-generated art, music and writing | Human art direction and review of every generated asset; label AI-assisted content; extra safety and age review because the audience is children |

**Agent workflow for a new animal world**

1. `codezoo world new <animal>` scaffolds `mse_codezoo/content/animals/<animal>/` with `SPEC.md`, `pack.json` and a first level; brainstorm with the model and fill in the spec.
2. One-shot a throwaway three.js prototype in chat to test the mechanic.
3. Run the coding agent against the spec inside the real engine (level JSON + animal pack, no engine changes), looping on `uv run codezoo levels validate` and `codezoo play` until every level passes.
4. Fun pass, then playtest with 3–5 learners; iterate.
5. Human review of art, text and concept accuracy; CI runs all reference solutions; publish.

## Risks, open questions and next steps

Parsing now uses CPython's own `ast`, so the biggest earlier risk shrinks to the interpreter drifting from real Python; it is contained by limiting the language to a documented subset and testing against CPython in the same pytest run. The new main risk is reach: until the offline browser build (phase 4), the web UI needs Python on the machine.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Children's personal data (EU GDPR parental consent; US COPPA if offered there) | Legal exposure; schools and parents lose trust | Progress stored only on the device by default, no tracking; parental consent before any cloud sync, account or sharing; privacy review before launch |
| Classroom hub can't be reached (Public network firewall on the teacher's laptop, device isolation on school Wi-Fi) | Children can't join; a teacher without admin rights can't fix it | Detect and explain it when the hub starts; a travel router for own workshops; a no-hub mode with links and files for ordinary teachers; IT installs the teacher app for adopting schools (see "Still open for phase 5") |
| Shared classroom and family devices | Children overwrite each other's progress | Several on-device profiles with picture login, no accounts; export/import per profile |
| Content from strangers via sharing and community packs | Unsafe content reaching children | Class-only sharing via teacher at first; reviewed, curated community packs; report button |
| Python subset behaves differently from CPython | Learners learn wrong rules | `tests/test_differential.py` runs every test program in our interpreter and in an isolated CPython subprocess and compares output |
| Web UI needs Python installed until phase 4 | Families, iPads and Chromebooks cannot play early | One-line install (`uvx --from mse-codezoo codezoo serve`) for pilots; keep the engine stdlib-only and import-test it in Pyodide from phase 2 so phase 4 is packaging, not porting |
| Engine and web client drift (two languages) | Sync bugs between Python and JS | The client only edits IR JSON; JSON schema for the IR generated from `ir.py` and checked on both sides |
| Time limits feel like punishment | Children stop enjoying it; parents switch them off | Finish the current run, goodbye animation, no countdown timer on screen |
| Camera for card scanning | Privacy worries | Optional, processed on the device, never stored; typed word code as an equal alternative |
| Host Python older than a release island | Island syntax cannot be parsed | Island shows as locked with an explanation; development pinned to the newest Python |
| Code → blocks fails for unusual code | Sync feels broken | Grey "raw code" block; never discard what the learner typed |
| Concurrency too abstract for younger learners | Module 14 drop-off | Lanes + timeline; modules 13–14 are optional and recommended from age 13 |
| No framework means more hand-written UI | Slower UI work | Small internal helpers (DOM builder, store, router), written once in phase 0 |
| Content volume (14 modules × \~12 levels, six animals) | Art and writing bottleneck | Core levels re-skinned by animal packs, only about 4 signature levels per module; level editor from phase 3 |
| Scope larger than the team | Phases slip, quality drops | Team assumption and effort per phase in the roadmap; MVP limited to the monkey and modules 1–5; cut optional modules 13–14 first |
| Interpreter grows into "all of Python" | Phases 3–4 slip | Documented subset per module; add constructs only when a module needs them; anything else becomes `RawCode` that is explained, not run |
| Building a block editor from scratch | Months lost on drag, touch and accessibility | Blockly spike in phase 1, decision at the gate |
| Touch drag-and-drop on tablets | Frustration on iPad | Pointer Events only, large hit areas, test on devices from phase 1 |

**Open questions**

- ~~Age hand-over~~: decided (Nov 21, 2026), no age rule. When every cub level is solved, the Grown-ups area asks "Ready for the main course?" and the grown-up decides; nothing is said to the child.
- ~~Free or paid; open source or closed?~~ Decided: free and open source, donations welcome, no cloud sync or accounts (see [Future improvements](#3-free-or-paid-open-or-closed)).
- Which interface languages at launch (English only, or translations from the start)?
- Should module 14 use real `threading`, `asyncio`, or both? Plan assumes `asyncio` first, threads shown as a comparison.
- Web UI delivery: keep the local server (`codezoo serve`) as the phase 1 client, or go Pyodide-first and skip the server? The plan assumes the server first because it is simpler to debug.
- Is the terminal client only for developers and adult beginners, or also a "hacker mode" for older children?
- Parent gate: is a written grown-up question enough, or is a PIN required by default?

**First steps (phase 0, weeks 1–4)**

- [x] `uv init --package`, switch to flat layout (`mse_codezoo/`, `tests/`, `module-root = ""`), `uv add click`, `uv add --dev pytest ruff`, pin Python (3.14 for now: uv 0.11.14 only offers 3.15.0b1; move to 3.15 after `uv self update`)
- [x] `codezoo` click group with `--version` and stubs for `run`, `check`, `levels`, `blocks`; `test_cli.py` with `CliRunner`
- [x] CI (GitHub Actions): `uv sync --locked`, `uv run ruff check`, `uv run pytest`, `uv run codezoo levels validate --all` on Python 3.11 and 3.14
- [x] IR dataclasses with JSON round trip for the phase 0 subset: calls, variables, `+=`, `for`, arithmetic, comments, `pass`, `RawCode` (`mse_codezoo/ir.py`)
- [x] JSON schema for the IR (draft 2020-12), generated from `ir.py` by `codezoo schema`, bundled as `mse_codezoo/ir.schema.json`; tests keep the copy in sync and check valid and invalid programs
- [x] `ast` → IR converter with kid-friendly errors and `RawCode` fallback that keeps the learner's text (`lang_python.py`)
- [x] Python printer with source maps (statement level; expression spans later); round-trip and stability tests
- [x] Generator-based interpreter for sequences, `for`, variables; step limit, number and text size limits, builtins whitelist (recursion limit comes with functions in phase 3)
- [x] Differential test harness against CPython (`tests/test_differential.py`)
- [x] Grid world with the monkey (`step`, `turn_left`, `turn_right`, `grab`, `say`), animal pack, plain-text renderer for `run --trace`, goal checks and stars
- [x] Six sample levels with reference solutions: five sequence levels (module 1) and one loop level (module 2); `codezoo levels validate --all` runs every solution

Moved to phase 1 with the web prototype: block editor spike (Blockly vs. own), three-pane layout with splitters and phone tabs, device testing on a laptop, an Android tablet and an iPad.

**Phase 1 steps (weeks 5–8)**

- [x] `codezoo serve`: stdlib HTTP server on localhost with a JSON API (`/api/levels`, `/api/levels/<id>`, `/api/parse`, `/api/print`, `/api/run`); request size limit; no files served outside `mse_codezoo/web/`
- [x] Web client in plain ES modules, no framework: three panes (stage, blocks, code), phone tabs below 800 px, light and dark colours
- [x] Simple 2D stage in SVG: grid, rocks, items, animal with a facing arrow; animates move, turn, grab, say and bump; speed slider
- [x] Blockly spike (13.3.0, Zelos renderer): monkey blocks for modules 1–2 (`step`, turns, `grab`, `say`, `repeat … times`, `#` note) and a grey raw block that keeps unsupported code as IR
- [x] Blocks ↔ IR mapper in `web/blocks.js`; block ids = IR statement ids, so run steps light up the code line and the block together
- [x] Sync: blocks → engine prints code; typed code → engine parses → blocks rebuilt, or kept when the code doesn't parse; code read-only unless "let me type" is ticked or the level mode allows typing
- [x] Blockly 13.3.0 vendored into `web/vendor/blockly/` (npm checksum verified, Apache-2.0 licence kept, icons local); the page loads nothing from the internet
- [x] Draggable splitters between the stage, blocks and code (mouse, touch and arrow keys; double-click or Home resets; sizes remembered per browser); Blockly dark theme that follows the system setting
- [x] Players with picture login (`profiles.py`): progress, best program, attempts and mistake kinds saved per player as JSON in the user-data folder (`CODEZOO_HOME` or `codezoo serve --data-dir` to change it); "Just try it" guest mode saves nothing
- [x] First grown-up gate: a multiplication question in words plus an optional PIN (salted PBKDF2 hash); panel with daily limit, private mode, PIN, per-player concept report with a "try at home" tip, export and remove
- [x] Daily limit: the page counts playing time per player; when the limit is reached the current run finishes, then a goodbye screen appears and Run is disabled until tomorrow
- [x] CLI: `codezoo profile add/list/remove/export/import`, `codezoo parent show/set/pin/report`, `codezoo check --profile NAME`
- [x] Levels: module 1 has 12 levels, module 2 has 11, including 4 debugging levels whose starter program has a bug to fix; level files take a `starter` program
- [ ] Playtest with 5–8 children aged 8–12; record the Blockly and Cub mode decisions
- [ ] Device testing: laptop, Android tablet, iPad

**Phase 2 steps (weeks 9–14)**

- [x] Interpreter: `if` / `elif` / `else`, `while`, comparisons (chained, `is`, `in`), `and` / `or` / `not`, `x if c else y`, `**`; text: f-strings with `!r` and format specs, indexing and slicing, a whitelist of text methods, `.format()` limited to `{}` and `{0}`, `print(sep=, end=)`, `type()`; size guards on powers, padding and format widths; IR version 2 with the new nodes, schema regenerated
- [x] Python adapter: parse and print the new nodes (precedence, right-associative `**`, `elif` with its own source-map span, comments on `else:` kept, f-string quoting that 3.11 can read); round-trip and CPython differential tests for all of it
- [x] World sensors `is_blocked()`, `item_here()`, `item_ahead()` (item names stay English in programs: `"banana"`), with `sense` events the stages animate; friendly error for `if is_blocked:` without brackets
- [x] Goals `say` (one text or an exact sequence), `avoid`, `all`, and `collect_all` with `avoid`; levels can have several worlds (`variants`): the run shows one, and the level counts as solved only when the program solves every world
- [x] Monkey modules 3–5: Variables (11 levels), Types and text (12), Conditions (11, most with 2–3 worlds), each with debugging levels whose starter must still need fixing; 57 levels in all, every reference solution earns 3 stars in every world
- [x] Feelings: proud, happy, puzzled, oops, confused or dizzy after each run, with growth-mindset messages; debugging levels frame a bug as "help the puzzled monkey"; shown on both stages and in the terminal
- [x] English and Slovak: engine messages through `t()` with `mse_codezoo/locale/sk.json` (tests require every message translated with the same placeholders), Slovak noun forms in the animal pack, level titles and hints per language, web interface and block labels in `web/i18n.js`, language menu, `?lang=` / `Accept-Language` on the server, `codezoo --lang sk`
- [x] three.js r170 vendored (npm checksum verified, MIT licence kept): low-poly 3D stage built in code (monkey, rocks, bananas, coconuts, plants, goal flag), camera fitted to the board and window, `prefers-reduced-motion` respected; the 2D SVG stage stays as the low-detail option and the fallback without WebGL
- [x] Blocks with value sockets: variables (set, change, get), numbers, text, maths, comparisons, `and` / `or`, `not`, sensors, `str()`, text methods, `if`, `if … else` (`elif` nests in `else`), `while`; plain values are shadow blocks; any other expression becomes a grey raw value block that keeps its IR
- [x] `codezoo play`: terminal client with a coloured, animated grid, one program file per level, run / edit in `$EDITOR` / watch for saves / hints / worlds / level list, progress and daily limit per player; ASCII fallback on consoles that can't show ★
- [x] Grown-up report: new mistake kinds (endless loops, mixing up types) with try-at-home tips; concept names and statuses translated
- [x] CI job imports the engine wheel in Pyodide 0.29.5 (Python 3.13) and solves every level there (`scripts/pyodide_smoke.mjs`)
- [x] ~~Cub mode for modules 1–2: waits for the phase 1 gate decision (no pilot yet), so not built~~ Built in phase 7 as its own two cub modules
- [ ] Slovak texts reviewed by a native speaker who teaches children; recorded narration (open point, does not block finishing phase 2)
- [ ] Pilot against the MVP metrics; device and performance testing of the 3D stage on the cheapest target tablet and Chromebook
- [x] Decide free or paid, open or closed before the pilot: free and open source, donations welcome (see [Future improvements](#3-free-or-paid-open-or-closed))

**Phase 3 steps (weeks 15–24)**

- [x] Interpreter: `def` with inputs, defaults and keyword arguments, `return` (several values as a tuple), local scope, closures, `global`, `import` / `from … import` of helper files (the level's own `files`, or the learner's `.py` files next to the program), recursion with a depth limit of 40 and a "base case?" message; `break` / `continue`; `try` / `except` / `else` / `finally`, `raise`, bare `raise`, `assert`, with real Python exceptions so `except` matches CPython (the zoo's limits stay uncatchable); lists, tuples, dicts, sets, unpacking with `*rest`, `del`, subscript assignment, list/dict/set comprehensions, collection methods and builtins (`sorted` with `key=`, `enumerate`, `zip`…); size guards for collections; the interpreter now runs statements directly (an emit callback replaces the generator) so learner functions can produce steps; uncaught errors keep a traceback (function, line) from the outside in; IR version 3, schema regenerated
- [x] Python adapter: parse and print every new node (bare tuples in `a, b = b, a` and `return`, `except (A, B) as e`, comments on `except` / `else` / `finally` lines kept as notes, starred items, comprehensions); round-trip and CPython differential tests for all of it (`tests/test_phase3_language.py`)
- [x] Animals: penguin, beaver and fox packs (English and Slovak names, their own item names, `catch()` for the penguin); terrain tiles (`~` water or gap, `t` tree, `-` thin ice, `o` a guard's watch, `=` bridge) and items on terrain; tricks: monkey `swing()` / `climb()`, penguin `slide()` and `CrackError`, beaver `build(log)` / `inventory()`, fox `sniff()` / `hide()` / `guard_ahead()`; a `build` goal
- [x] Core levels re-skinned for every animal: programs, helper files and hints follow the chosen animal (`reskin_source`), the web has an animal picker, signature levels (`"signature": true`) stay with their own animal; validation refuses terrain or tricks in a core level and runs every core solution as every animal
- [x] Modules 6–10: Loops II (11 levels), Functions (12), Errors and debugging (9), Collections (10), Recursion (10); 109 levels in all, with debugging levels in every module and signature levels for all four animals; Slovak titles and hints; every reference solution earns 3 stars in every world, for every animal that can play it, in CPython and in Pyodide
- [x] Blocks for the new constructs: `break`, `continue`, `def`, call (statement and value), `return`, `try` / `except`, `raise`, for each, list (up to 4 items), `append`, `len`, `[ ]`, `.get()`, `.items()`, `import`, `global`, and the animals' tricks; anything else stays a grey raw block
- [x] Stages: penguin, beaver and fox models and every pack's items in 3D, ground per world, water, trees with fruit on top, thin ice, guard posts, bridges; swing, climb, slide, build, crack and hide animations in 3D and 2D; the call stack under the stage as nested burrows while a program runs
- [x] Saved runs (`*.run.json`): `codezoo run --save`, "Save this run" in the web; `codezoo replay RUN` replays one in the terminal
- [x] Storybook: narration generated from a run's events with a picture per page, an editable title and an editable line per page, printable; `codezoo story export`, "Make a storybook" in the web; English and Slovak
- [x] Printable unplugged cards per animal and module (`codezoo cards print`, `/cards.html`), each with a word code and a QR code from a small stdlib encoder (checked against an independent QR reader); typing or scanning a code (camera only where the browser can read QR codes, nothing stored) unlocks a sticker and opens the level; `codezoo cards unlock`
- [x] Stickers and habitat: stickers for the first solved level, finished modules, star milestones and cards; "My zoo" places them in the habitat by dragging, and outfits unlocked by sticker count show on both stages; kept in the player's progress and export
- [x] Adaptive suggestion: after 3 failed tries on a level, an earlier level that practises the same concept (fewest stars first) is offered in the web and the CLI; the child can still pick freely
- [x] Level editor prototype (`editor.html`): tile painter with terrain, start, flag and items on trees, goal, hints, starter and solution; "Test the level" runs the same checks as `levels validate` (`POST /api/levels/check`); download the level JSON and solution file; open an existing level file
- [x] `codezoo world new ANIMAL` scaffolds `SPEC.md`, `pack.json` and a first signature level
- [x] Grown-up report: new mistake kinds (endless recursion, uncaught errors) with try-at-home tips
- [x] Tests: `test_phase3_language.py`, `test_phase3_features.py` and `test_web_i18n.py` (every web text has a Slovak translation); the Pyodide CI job solves all 109 levels
- [ ] Fewer levels than planned in modules 8–10 (9–10 instead of about 12) and fewer signature levels per module (1–4 instead of about 4); to be filled with the level editor once content production starts
- [x] Generators, `lambda` and generator expressions moved with module 11 to phase 4 (done there)
- [x] Graduation path: `codezoo graduate` (phase 4) exports a plain `.py` and can run it in CPython
- [ ] Recorded narration for the storybook and voices for cards (speech synthesis first); a native-speaker review of the new Slovak texts (same open point as phase 2)
- [ ] Learning-gain and drop-off check with pilot families (the phase 3 gate); device testing of the new 3D animals on the cheapest tablet

**Phase 4 steps (weeks 25–36)**

- [x] Interpreter, generators and lambda: `lambda`, `map` / `filter` / `iter` / `next` / `StopIteration`, generator functions (`yield`, `.send()`, `yield from` with return values), generator expressions, endless generators; lazy iterators (`map`, `zip`, `enumerate`, `itertools`) count what they hand out, so an endless one stops at a limit instead of freezing. Pausable bodies run as Python generators only where a statement holds `yield` / `await` (everything else still runs directly), so the step-by-step interpreter stays as fast as before
- [x] Interpreter, objects: classes become real Python classes (so `isinstance`, the MRO, `super()`, special methods, `@dataclass`, `NamedTuple` and the learner's own exceptions behave like CPython); learner functions bind as methods; a whitelist of special methods, hidden `__class__` and friends, and no three-argument `type()` keep a class from hooking into the interpreter; notes never run the learner's own `__repr__`
- [x] Interpreter, decorators: functions as values, `*args` / `**kwargs` in definitions and calls, keyword-only inputs, `nonlocal`, stacked decorators, decorators with arguments, class-based decorators (`__call__`), `functools.wraps` / `cache` / `lru_cache` / `reduce` / `partial`
- [x] Concurrency (`scheduler.py`): `async def` / `await`, `asyncio.run` / `sleep` / `create_task` / `gather` / `Lock` / `Queue` / `TaskGroup` (cancelling siblings) and `except*`, on a simulated clock in CPython's own task order (differential tests against real asyncio); `threading.Thread` / `Lock`, statement by statement with a seeded scheduler, with or without the GIL (3.13 free threading: threads overlap in the same tick), deadlock detection; every step carries its lane and tick
- [x] `with` (several items, own context managers, `async with`), `match` / `case` (literals, captures, sequences with `*rest`, mappings, class patterns via `__match_args__`, `|`, guards, `as`), type hints kept and never run, `input()` (answers from the level) and `open()` on a per-run in-memory disk, `if __name__ == "__main__":`, the zoo's own `math`, `random` (seeded), `json`, `string`, `time`, `itertools`, `copy`, `dataclasses`, `typing`, `__future__`; IR version 4 (21 new node types), schema regenerated
- [x] Release islands (`versions.py`): a `since` table for syntax and builtins; programs are checked against a chosen release (`--python`, a menu in the web client) and refused with the release that brought newer syntax; levels take `"minPython"`; islands newer than this computer's Python show as locked and `levels validate` skips them. Islands: baseline 3.10/3.11 (5 levels: `match`, `zip(strict=)`, unions, parenthesised `with`, `except*`), 3.12 (3: nested f-string quotes, `class Stack[T]` / `type`, `batched`), 3.13 (2: free threading with and without the GIL, `copy.replace`), 3.14 (3: template strings, `except A, B:`, deferred annotations), 3.15 (4: `frozendict`, `[*x for x in xs]`, `sentinel`, `lazy import`). The 3.15 levels were checked on CPython 3.15.0b1; CI adds 3.15 to the matrix
- [x] Animals: octopus (`await reach(arm)` stretches one of eight arms while the others keep working; `stretch(arm)` for threads) and bee (`fly(n)` over rocks, water and trees), with English and Slovak names, 3D models and 2D drawings; new goals `print`, `file` and `time` ("done by tick N"), and a hint when a trick was started without `await`
- [x] Modules 11–15: Comprehensions and generators (9 levels), Objects (9), Decorators (8), Concurrency (8), First real project (6), with debugging levels in every module, signature levels for the bee, fox and octopus, Slovak titles and hints; 166 levels in all, every reference solution earns 3 stars in every world for every animal that can play it
- [x] Lanes under the stage: one row per task or thread on the simulated clock, bars while a lane waits, steps of the same tick played together (the octopus's arms move at once), and a timeline slider that jumps to any moment
- [x] Blocks: `class`, `async def`, `yield`, `await`, `await reach(arm)` and the bee's / octopus's tricks; an outline block keeps a header the blocks can't show (decorators, `with`, type hints, `async`) exactly as typed while its body stays blocks, so code-first modules read as an outline and nothing is lost either way
- [x] Offline browser build (`codezoo build-web`): the same web client with the engine in Pyodide 0.29.5 in a web worker, calling the server's `dispatch()` directly; a service worker caches the site and Pyodide; players' progress in IndexedDB; cards pre-rendered; host it on any static host. CI builds it and solves every level and calls the API inside Pyodide
- [x] Level editor, full version: several worlds, every goal type plus "done by tick", answers for `input()` and files for `open()`, a no-GIL switch, Python release, Slovak title and hints, "My levels" kept in the browser, and share links that carry the level inside the link (nothing uploaded; the game checks it like a level file and runs it only in the zoo's interpreter)
- [x] Graduation: `codezoo graduate PROGRAM.py [--run]` writes a plain `.py` (the zoo's commands become stand-ins that print) and runs it in CPython, for the learner's own programs only
- [x] Tests: `test_phase4_language.py` (every construct against CPython, round trips, limits, safety), `test_phase4_features.py`; the suite passes on Python 3.13, 3.14 and 3.15
- [ ] Gate: run the offline build on the cheapest target tablet and Chromebook (not done; only checked in a desktop browser), and pilot modules 11–14 with learners aged 13+
- [ ] The first visit to the offline build needs the network for Pyodide (about 10 MB); a vendored Pyodide copy (`--pyodide ./pyodide/`) works but isn't packaged yet
- [ ] Fewer levels than planned: 6–9 per module instead of about 12, 2–5 per island; to be filled with the editor
- [ ] Not built: the 3.13 REPL "pond", `concurrent.interpreters` (3.14), a free-threading boss level, rival levels; `async for`, async generators and `:=` stay raw code; `lambda`, `match` and `with` have no blocks of their own (outline or raw)
- [ ] Concurrency is simulated: threads switch only between statements (a call inside a thread runs in one go), and `lock.acquire()` in a thread waits after its line; good for teaching races, not a model of real CPU timing
- [ ] Native-speaker review of the new Slovak texts, recorded narration (same open point as phases 2 and 3)

**Phase 5 steps (decisions of Nov 21, 2026; built Nov 21, 2026)**

No cloud and no accounts. The teacher's computer runs a classroom hub on the local network for one workshop or class. Children's devices join it with a class code and a picture.

- [x] Classroom hub: `codezoo class serve NAME` runs the usual web server on the local network (`--host 0.0.0.0` by default; `codezoo serve` stays on localhost), only while the teacher keeps it running. A hub layer (`hub.py`) checks the class code or the teacher's key, then passes the usual routes to `server.dispatch`; the grown-up routes and the family player list are closed in a class. The request size limit and the rule against serving files outside `web/` still apply; level ids in the address are checked so they can't name a file
- [x] Teacher's screen (`teacher.html`): opened with a teacher's key that `class serve` prints as part of the teacher address (a new key every start), *instead of the grown-up gate and PIN in the draft*: the gate's sum is no protection on a shared network, and a PIN would have to be typed on the projected screen. The key is kept in the teacher's browser, so the level editor works there too
- [x] Class code: a word and a number (`RIVER-283`), new at every hub start, with "New code" on the teacher's screen; ending a class makes a new one, so the old code stops working. Ten wrong codes from one device in five minutes make it wait
- [x] Class type, picked when the class is created: **workshop** (children pick any picture, a first name optional, data deleted when it ends; *changed Nov 22, 2026*: names were off and each picture could be taken once, but children want the same animal, so pictures may repeat and a name, or a number after the picture's name, tells them apart) or **class** (the teacher adds players, children pick themselves from the list, names on, data kept). The type sets the defaults; each setting can be changed on the teacher's screen or with `class new --names/--roster/--delete-at-end`
- [x] Joining: the child types the code (case, spaces and the dash don't matter) or scans the QR code, then taps their picture or picks one of 32 animals (several children may pick the same one) (the family picker keeps its 8), plus a first name if allowed. Without a name, a player is called after the picture ("Cat", "Mačka"). The teacher can add, rename and remove players
- [x] QR joining with the device's own camera app: the QR code (from the engine's own encoder) holds the hub's address and the class code; the page reads the code from the address and removes it from the address bar. Plain HTTP, no certificate, no camera access in the page
- [x] Joining by the hub address (the default). "Take my progress home" (child) and "Save to a file" (teacher) give a file in the `codezoo profile export` format; at home it loads in the Grown-ups area ("Load a player from a file", new) or with `codezoo profile import`, keeping the class picture. "Bring my progress from home" loads one into a workshop
- [ ] *Optional, deferred (build only if teachers ask for it):* the offline app (`codezoo build-web`) joins a hub with "Join a class". It would need the hub on HTTPS with a certificate each device trusts, CORS, and browsers allowing a public HTTPS site to reach a local-network address. Export and import files cover this until then. The offline build leaves out the teacher's screen
- [x] Class language (added Nov 22, 2026): the teacher picks the language children's devices open in (or each device's own); the QR code and the shared link carry `&lang=`, a typed address gets it from the hub, and a child can still switch. Language menus show a flag before each language (Windows draws the flags as the letters GB and SK)
- [x] Stage view per class (added Nov 22, 2026): the teacher ticks 2D, 3D or both; with one, every child's device uses it and the 3D switch goes away (2D only for slow tablets), with both each child picks. A device without WebGL always falls back to 2D
- [x] Per-child settings (added Nov 22, 2026): the class's stage view and language are the default; in the players table the teacher can set a child's own ("as the class", 2D, 3D or both; "as the class", the device's own, English or Slovak). The child's device asks for its player's settings when it polls, so a change arrives within a few seconds; a child who switched language keeps their choice until the teacher changes it. Removing a player removes their settings too
- [x] Teacher levels: added from "My levels" in the teacher's browser, from a level file with its solution file, from a child's shared level, or with `codezoo class add-level`; checked like `levels validate` first (and refused when a built-in level has the id); then picked for today like built-in levels, under "Our own levels"
- [x] Data: *changed from the draft*: in a class the progress lives on the hub (the teacher's computer), in the class's folder, stored exactly like a family's; the child's device keeps only the class code and which player was picked. This is what joining by the hub address means (the engine runs on the hub), and it needs no syncing. Export, deletion and "nothing to the internet" as planned
- [x] Teacher class view: per player stars, solved levels, a bar per module, minutes today and who is stuck (3 or more tries on an unsolved level); a per-player concept report; a class concept report (met / practised / mastered counts), the most common mistakes, and per level how many tried and solved (drop-off). The page redraws a part only when its data changed, so clicks aren't lost to the 5-second refresh
- [x] Workshop controls: tick today's levels per module, "Only these levels" (children see and run nothing else; the engine refuses other runs; *on by default since Nov 22, 2026*: once the teacher saves today's levels, children see only those, and with nothing saved they see every level. Turned off, the picks come first under "⭐ Today" and a child's page moves to the first one; a save button glows while ticks are unsaved, and "Start the lesson" / "Let everyone play again" stays disabled until the teacher saves or discards those changes, so children are only ever let in on a saved list. Today's levels can be changed only while the class is paused (a child might be in the middle of a level the new list removes); while children play the list is read-only, which the teacher's screen enforces, not yet the hub. The same goes for removing a player or one of the class's own levels, switching a child's Cub mode and "New code": disabled with "Pause everyone first" while children play. The pause button is red, the start / play button green), *a served class starts paused (Nov 22, 2026)*: children who join see "Getting ready…" until the teacher, after picking today's levels and settings, presses "Start the lesson"; "Pause everyone" (an "Eyes on the teacher!" screen on every device within 4 seconds; runs are refused while paused). "On the projector" shows a shared program big; the child's consent is that they shared it
- [x] Class-only sharing: *programs and levels* (a program after a run, a level from the editor), not saved runs or storybooks as drafted; a classmate's program opens with its level and code. Shares wait for the teacher's yes; "Tell the teacher" hides one until the teacher looks again. Size limits per share and per class
- [x] CLI: `codezoo class new/list/add-player/add-level/export/delete/serve`, and `class --data-dir PATH`
- [x] Privacy note for schools: [docs/classroom-privacy.md](docs/classroom-privacy.md) (what the hub stores, where, who can see it, how to delete it; plain HTTP only on a trusted network; no per-child passwords)
- [ ] Privacy review (the gate): the note above checked by someone qualified against GDPR (school as data controller), and against COPPA before any US use
- [x] Donations: a "Support" section with a Buy Me a Coffee link at the end of the README
- [x] Donations: the same link in the game's Grown-ups area (only after the gate) and on the teacher's screen, never on a child's screen (see [Future improvements](#3-free-or-paid-open-or-closed))
- [x] Tests: `tests/test_phase5_classroom.py` over real HTTP (codes, rate limit, teacher's key, roster, closed grown-up routes, file names in level ids, runs and the overview, today's levels, pause, own levels, shares, export to home and back, ending a class and a workshop, CLI). Checked in the browser on one computer (child and teacher tabs); not yet on a real school network or tablets
- [ ] Gate: one real workshop or class (about 10–25 children) runs a session on the hub, on a school network (device isolation on school Wi-Fi is the main risk), with the teacher's laptop and children's tablets

Still open for phase 5:

- ~~Offline build and the hub~~: decided, the hub address with export and import files by default; the offline app joining is optional and deferred (see above).
- ~~Roster~~: decided, it depends on the class type. ~~QR scanning~~: decided, the device's own camera app (no certificate). ~~Teacher levels~~: decided, yes.
- Concurrency: the hub answers one request at a time (a lock keeps the class's files consistent). Fine for a class on a laptop in a desktop browser test; measure with 25 devices running at once at the gate.
- A small packaged app for teachers (no Python or `uv` to install) would make the hub much easier to start on locked-down school laptops.
- **Weakness of the hub found on Nov 22, 2026: children's devices must be able to connect *to* the teacher's computer**, and on many networks they can't. In the first home test the phone reached the right address but got `ERR_CONNECTION_ABORTED`: Windows treated the Wi-Fi as a **Public** network, and Public networks block incoming connections unless a firewall rule allows them. The fix (make the network Private, then allow Python, or add a rule for port 8765) needs administrator rights. Two problems stack up at schools:
  - **Firewall and network profile.** School laptops are managed by IT, so a teacher usually can't change the network profile or add a firewall rule. The SmartScreen and firewall steps in `docs/pilot/teacher-app.md` assume an administrator.
  - **Device isolation.** Many school and guest Wi-Fi networks stop devices from reaching each other at all, so even an open firewall doesn't help (this is the risk named in the gate above).
  - So "the teacher's laptop is the hub" works only where someone with admin rights has set it up: the maintainer's own laptop for his workshops, or a school whose IT installs it. It is not a zero-setup tool for an ordinary teacher.
  - Ways forward, to decide before the gate: **(A)** no hub, so nothing connects to the laptop: children play the hosted offline version, today's levels go out as a link or QR code (share links already carry levels), and progress comes back as files (or a QR code per child) into a teacher's screen in the teacher's own browser; no live view, pause or live sharing. **(B)** a travel router (about €25) that makes its own Wi-Fi without device isolation; fixes isolation, not the firewall, so it suits the maintainer's own laptop. **(C)** the school's IT installs the teacher app with a firewall rule once (an installer that needs admin rights once, probably code-signed). **(D)** a preconfigured "CodeZoo box" (for example a Raspberry Pi) with its own Wi-Fi and the hub, which needs no setup on the teacher's laptop; a possible paid service for schools later.
  - Current lean (not decided): the hub as built plus a travel router for the maintainer's own workshops and the pilot; A as the default for teachers without IT help; C for schools that adopt CodeZoo. In every case, the hub should detect a Public network (and, if it can, blocked incoming connections) when it starts and print the fix in the terminal and on the teacher's screen, so a teacher learns why before 25 children are waiting.

**Phase 6 steps (decided and built Nov 21, 2026): pilot readiness, with accessibility basics**

Every gate from phase 1 on waits for a pilot with real children, and none has run yet. This phase removes what stands in the way: installing, measuring learning, collecting the pilot metrics, and the paperwork. It adds the accessibility a pilot school may ask for. It adds no new modules or animals.

*Getting it onto devices*

- [x] Families: `codezoo build-web site/ --pyodide-dir node_modules/pyodide` copies Pyodide into the site (`pyodide/`), so it loads nothing from a CDN, not even on the first visit. The "Pilot builds" workflow (`.github/workflows/pilot.yml`) builds and publishes it on GitHub Pages
- [ ] Switch Pages on for the repository (Settings > Pages > Source: GitHub Actions) and set the repository variable `CODEZOO_PAGES` to `true`; until then the publishing job is skipped. Not yet tried on a real Pages address
- [x] Teachers: `CodeZoo-Teacher.exe` (PyInstaller, about 11 MB, `scripts/build_teacher_app.py`; built by the "Pilot builds" workflow as an artifact) runs the new `codezoo teacher`: it lists the classes, makes a new one if asked, starts the hub and opens the teacher's screen. Checked on Windows: it serves every level and the web client. Not code-signed (SmartScreen and firewall steps in `docs/pilot/teacher-app.md`); macOS later
- [x] Device check page (`check.html`, also in the offline build): screen and touch, engine start (Pyodide in the offline build), one level run, the 3D stage's frames per second, free storage and the hub; below 25 frames a second it offers "Use the 2D stage on this device". "Copy the results" for the device checklist. Real numbers for the low-end budget come from the pilot devices

*Measuring learning*

- [x] Concept checks (`content/checks.json`): the same 3 questions before and after each of modules 1–5 (where does the animal stop, which program gets the banana, what does it say), English and Slovak, with code shown as code; *not pictures yet*. "Before" opens with the module's first level; "after" once 70% of the module is solved. Never scored in front of the child, and "Skip the questions" is recorded as skipped. The grown-up report shows right answers before and after per module. Marked `"reviewed": false` until a teacher has checked them; modules 6–15 later
- [x] Pilot metrics recorded on the device (`pilot.py`), only when a grown-up or the teacher turns "Take part in a pilot" on, and never in private mode: when the first level was opened and the first star earned, hints shown when each level was first solved, levels opened, the checks, errors the page saw (failed runs and blocks that couldn't become code), and *the smiley once a day under a solved level* (not at the end of a session: the page can't tell when a session ends)
- [x] Pilot export: Grown-ups area, teacher's screen and `codezoo pilot export`. It lists what the file holds and saves only after "I agree"; random pilot id (`P-7KX3MQ`) and age band (set per player by the grown-up or teacher), no names, pictures, programs or typed text (a test checks this). `codezoo pilot report FILES... [-o report.md]` merges files into the six pilot metrics with their targets (sync reliability is reported as an error count; enjoyment as the share of 4–5 smileys)

*The pilot kit* (`docs/pilot/`, English and Slovak)

- [x] `docs/pilot/`: overview and data flow, parent letter with consent form (English and Slovak; contact details and retention period are placeholders for the maintainer), facilitator guide, observation sheet, device checklist, teacher app guide. The guides are English only for now; the Slovak letter needs a native speaker's review

*Accessibility basics*

- [x] "Look and feel" (the "Aa" button on the game page and the teacher's screen, `look.js`, kept per browser, applied on every page): text size (normal, large, larger), easy-to-read text, high contrast (light and dark), motion (as the device is set, less, all), big targets (48 px buttons, bigger picture tiles, blocks at 125%, and a tap on a palette block adds it to the end of the program). *Easy-to-read uses system fonts with more spacing, not a bundled dyslexia font* (the page loads nothing from the internet; bundling OpenDyslexic is open). Animation speed stays the existing Speed slider. *Nov 25, 2026:* the saved look is put on the page by a plain script at the top of each page's `<head>` (`web/early-look.js`) before it is first drawn; before, a page set to dark showed light colours for about a second while its modules loaded
- [x] Keyboard: every control is a real button, select or input, and dialogs close with Escape. Blockly 13 has keyboard navigation built in. *Not yet checked end to end with only a keyboard*, on any page
- [x] Screen readers, first step: results, feelings, hints and errors are live regions; the stage has a text description (size, where the animal is and which way it faces, items, rocks), updated for each world. *Not yet tried with a real screen reader* (NVDA, VoiceOver, TalkBack). Full screen-reader editing of blocks stays for later
- [x] Tests: `tests/test_phase6_pilot.py` (opt-in, private mode, events, every question complete, checks before and after, the export holds nothing private, age bands, the report against targets, CLI, the hub, levels by id only, bundled Pyodide, the Look and feel button). Checked in the browser: pilot switch, the questions, the smiley row, Look and feel with big targets and tap-to-place, the device check
- [x] Found while building: API requests now name levels by id only (`find_level` also takes a file path, which a class on a network must not reach), and the grown-up route accepts `-` in action names

- [ ] Gate: the first pilot (5–8 children aged 8–12, 30 minutes each) runs with the kit on real devices and returns its metrics file

Open points for phase 6 (to discuss before building):

- ~~Who receives pilot files~~: decided (Nov 21, 2026), only the project maintainer, who is then the data controller for pilot data. Consequences for the build and the kit:
  - Collect as little as possible: a random pilot id per player, age band (not birth date), module and level ids, counts, durations, concept-check answers and the smiley; no names, programs, free text, device names or IP addresses. Even so, treat the files as personal data (pseudonymous, and a small pilot makes people easier to recognise)
  - Files reach the maintainer only by hand from the parent or teacher (a file they choose to send); the app never uploads anything
  - The consent form and parent letter name the maintainer as the contact, say what is collected and why, how long it is kept, and how to ask for deletion (the pilot id is shown on the export screen so a family can quote it). The contact details are filled in by the maintainer, not written into the code
  - Keep raw files only until the pilot report is made, then keep only the merged, aggregated table; write the retention period into the kit
- ~~Hosting~~: decided, GitHub Pages now (a workflow builds and publishes the family version once Pages is switched on for the repository); its own domain after the trademark search
- ~~The teacher app~~: decided, an unsigned Windows build first, with a short guide to the one-time SmartScreen warning; macOS (needs notarisation) and code signing later, when a school needs them
- ~~Concept-check questions~~: decided, drafted here for modules 1–5 (the pilot's scope) and marked for review by a teacher; modules 6–15 later
- ~~Accessibility scope~~: decided, the list above

**Phase 7 steps (decided and built Nov 21, 2026): Cub mode and read aloud**

Cub mode has waited since phase 1 for a pilot that hasn't run. It is built now as an option per player, so the first pilot can include 6–8-year-olds. Read aloud is built with it: cubs need it, and it is the accessibility step phase 6 left out. No new runtime: Cub mode is a face over the same engine, blocks and program model.

Decisions (Nov 21, 2026): Cub mode is set **per player** (siblings on one device can differ); cubs get **new cub levels**, not the existing modules 1–2 with icons; **the grown-up decides** when to move on (no age rule, nothing said to the child); read aloud is **on in Cub mode and an opt-in for everyone else**, with the device's own voices only.

- [x] Cub levels (`content/levels/cub1-sequences/`, `cub2-loops/`): two modules of 10, "Cub: steps and turns" and "Cub: repeat", on grids of at most 6 × 4 with 1–7 blocks. Each module follows the simplified PRIMM pattern from the Cub mode section: **predict** (the reference solution is shown; the child taps the square where the animal will stop, then runs it; the goal flag is hidden), **fix** (one wrong block in the starter), **make**. A level's `"cub"` key names its step; validation checks that cub levels sit in a `cub-` module, that fix levels have a starter and predict levels don't. English and Slovak titles and hints; every solution earns 3 stars for every animal
- [x] Per-player switch: `Profile.cub`; a "Cub mode for ages 6–8" box when a player is added; the switch in the Grown-ups area (behind the gate, `POST /api/parent/cub`); on the teacher's screen per child (`/api/teacher/player/cub`) and "New players start in Cub mode" for the class; `codezoo profile add --cub`, `codezoo profile cub NAME --on/--off`, `codezoo class add-player --cub`. Export and import keep it; older player files read as "off"
- [x] Two courses kept apart: cubs see only the cub levels (big numbered buttons with stars instead of the level list), everyone else never sees them; practice suggestions and the concept report stay in the player's own course; finishing a cub module gives its own sticker. A teacher's "today's levels" without any cub level shows a cub everything picked
- [x] Picture blocks: 👣 step, ↺ / ↻ turn, ✋ grab, 🔁 repeat (the loop variable hidden), the same block types and IR, so code and blocks stay in sync. Big blocks and tap-to-place are always on in Cub mode. No typing, no Python release menu, no level editor link, and the star rules ("no line limit") are hidden; the stars, feelings and storybook stay
- [x] Colour-linked code pane: each block's lines are tinted in its family colour with a bar whose pattern also names the family (motion solid, action dashed, loop dotted, say double), so colour is never the only signal; lines inside a loop are indented so the loop's bar stays visible; new lines glow for a second (not with less motion); tapping a code line makes its block glow and reads it aloud
- [x] Read aloud (`web/speech.js`): goals, hints, results with the feeling, the predict question and answer, and tapped blocks ("Repeat 3 times: step 1, grab"), with the browser's speech synthesis and the device's own voice for the page's language (offline voices first); emoji and stars are left out of what is spoken. On in Cub mode with a 🔊 "read it to me" button and a mute button kept per browser; for everyone else "Read aloud" in Look and feel. *Without a voice for the language nothing is read*, and Look and feel says so with a "Try the voice" button
- [x] Grown-ups: the report shows "Cub levels: N of 20 solved" and, once all are solved, "Ready for the main course?" with a button that turns Cub mode off
- [x] The terminal client (`codezoo play`) leaves the cub levels out: they need pictures and a voice
- [x] Tests: `tests/test_phase7_cub.py` (the levels and their pattern, validation, every solution for every animal, the predict program, the switch with the PIN, the new-player box, old files, export and import, the ready report, stickers, suggestions, the hub, the CLI, the web pieces, read aloud without any network, the offline build). Checked in the browser at tablet size: switching on and off, a right and a wrong prediction, a fix level, picture blocks, tap-to-place, tints and the glow, what is spoken (English; this computer has no Slovak voice, so Slovak correctly says nothing), the teacher's column and class setting
- [ ] *Not built from the Cub mode section*: free Story mode (no goal), "help the confused penguin" framing beyond the existing feelings, co-play prompts for grown-ups, ghost icons at the end of code lines, mini-games on the code pane, cub levels for the other animals' tricks and for conditions (age 7+), recorded voices
- [ ] Not checked: real Slovak voices (Windows, Android and iOS each have their own; many devices have none), speech on the cheapest tablet, children who can't read using it without help
- [ ] Gate: 3–5 children aged 6–8 play the cub modules with a grown-up nearby (the pilot kit's facilitator guide needs a short cub section); read aloud is tried on the pilot devices in English and Slovak

**Phase 8 steps: game mode** (see [Future improvements, section 4](#4-game-mode-children-make-their-own-games))

*G0 spike (built Nov 24, 2026)*

- [x] Engine: `gamemode.py`. The program runs once to set up, then `on_key(key)`, `on_tick()`, each critter's `on_tick(self)`, `on_item(item)` and `on_touch(critter)` run on every tick, in that order. Programs also get `Critter`, `score`, `win()`, `lose()`, `go(direction)`, `where()`, `ticks()` and `critters()`; without an `on_key` the arrows move the animal
- [x] Integer-only game state: grid squares and whole ticks; floats only for drawing. Same program, seed and keys give the same game (`Game.inputs` is all a replay needs)
- [x] A critter's place is kept by the game, not on the object: programs read `self.x` but move only with `step()`. A class that forgets `super().__init__(x, y)` gets a kind message
- [x] Bumps never crash a game (the animal or critter stays put). Each tick has a budget of 1,000 interpreter steps for all handlers together; a runaway loop ends the game with "The game got tired: … Is a loop running forever?" and the line marked
- [x] Game files in `content/games/*.json` (world, animal, rules: `collect_all`, `{"score": N}`, `{"survive": N}`, `caught`, `max_ticks`, starter, help per language); first game: `collect-guard` (bananas and a patrolling guard)
- [x] API: `GET /api/games`, `GET /api/games/<id>`, `POST /api/game/start | tick | stop`; running games stay in memory (`Sessions`, newest 32) on the server or in the offline build's web worker. On a classroom hub, "pause" stops games too
- [x] `game.html`: 2D board (emoji that slide between squares; still with "less motion"), arrow keys and an on-screen pad for touch, code with line numbers that light up per tick, error line marked, printed output, help, the program's API at a glance; draft code kept per game in this browser; English and Slovak; "Make a game" link on the main page; part of the offline build
- [x] Tests: `tests/test_phase8_games.py` (bundled games, rules, handlers, critters, bumps, budget, errors, determinism, speed, API, sessions)
- [x] **Measured (Nov 24, 2026), 5 patrolling critters:** CPython about 3,000 ticks a second (0.3 ms a tick, about 15 interpreter steps a tick). Offline build in the browser (Pyodide 0.29.5, desktop, including the round trip through the web worker and JSON): about 1,100 ticks a second (0.9 ms a tick). A game needs about 7 ticks a second (150 ms a tick), so even a tablet 20× slower has a big margin. **Decision: keep the Python interpreter** (see "G0: language and performance"); no closure compiler needed for now. The playtest bot (300 games × 200 ticks = 60,000 ticks) would take about a minute in the browser at this speed: run it on the hub or play 30 games in the browser (G1)
- [x] 3D stage for games (Nov 24, 2026): the zoo's three.js stage gets `loadGame`, `showGame` and `bumpGame`; the animal and the critters glide to their new square within one tick, removed critters shrink away, items vanish when grabbed. Critter models per kind: the zoo's animals (`fox`, `bee`…), a crocodile for `guard`, a ghost, and a spotted beetle in a colour picked from any other kind's name. A 2D/3D switch on the game page (remembered in this browser); three.js loads only when 3D is picked, and without WebGL the flat board is used. Less motion: no hops, near-instant glides
- [x] Sounds (Nov 25, 2026, after G3): made on the spot with Web Audio like the rest of the fun pass (`fun.js`), following the Sounds switch (🎵 on the game page, the teacher can lock it): grabs climb a little scale, bumps, touches, doors, switches, power-ups, building, win and lose; programs play their own with `sound("ding")` (ding, boing, pop, drum, whoosh, tada, oops, click; at most 4 a tick from the engine and 3 a tick on the device). Comfort limits: soft volumes, no shrill notes, short sounds
- [ ] *Not built in G0*: blocks for game handlers (code only), the classroom hub's 2D/3D class setting for games (each child picks), game-state music (`music.tempo`)
- [ ] Not checked: the cheapest target tablet; touch play on a real tablet; the hub over school Wi-Fi with a tick every 150 ms per child
- [ ] Gate: the game runs smoothly on the cheapest target tablet (2D) and 3–5 children aged 9–12 change the starter game and play it

*G1 Make a game, alone (built Nov 25, 2026)*

- [x] Four templates, one core rule each, in lesson order: collect (`collect-guard`), dodge (`dodge-bees`), chase (`chase-frogs`), maze (`maze-ghost`); game files gain `template`, `lesson` (the nearly empty program the rounds start from) and `rounds`
- [x] Lesson rounds: five per template (move with keys → collect and score / a critter that moves → the critter catches you → … → "make it more fun"), each with a goal, a "Show me how" code hint and `needs`; a round is done when `Game.features()` has what it needs (the program's handlers, `critter`, `critters2`, `critter_tick`, `object`, and every name in the code). Done rounds are kept per game in this browser
- [x] Twist cards for the last round (`gamemode.twists()`): speed-up, a second critter, power-up, secret door, each with code to start from and its own `needs`
- [x] Design card on the game page: "My game in one sentence", "How do I win?", "How do I lose?"; kept per game in this browser and sent along when a game is shared, so the teacher sees it before approving
- [x] "Test my game" (`gamemode.playtest`, `POST /api/game/test`): collector, chaser and wanderer bots (breadth-first walks around critters, seeded, deterministic) play 30 games in the offline build and 60 on a server; kind reports for nobody can win (no rule, too hard, caught too often), too easy, a hard game, items nobody can reach, the line where the game broke, and "this device is slow" when a time limit stops it early. The bot found three real problems while the templates were made: G0's starter broke on the space key (`go("space")`), the penguin's `catch` broke `grab()` in games (now every animal also gets the plain command names in games), and the first dodge game was too hard
- [x] Each game opens with its own animal (G0 always opened with the first in the list)
- [x] "Which handler fired?" (Nov 25, 2026, after G3): every tick says which handlers ran, how many times (every critter's `on_tick` is one line), how many steps they took and what each changed (`fired`: the animal, score, items, critters, built squares, doors, won or lost, printed, sound), from a snapshot before and after each handler. The game page shows it as a table, a row per tick (newest on top, 30 kept) and a column per handler, with an emoji for each change; it works for shared worlds too
- [ ] Not built: debugging levels where handlers fight over `score`, game-state music
- [ ] Gate: 5 children make and finish a game in one session and want to make another

*G2 Game editor and sharing (built Nov 25, 2026)*

- [x] Objects with attached scripts: a world's `objects` (`{"at": [x, y], "class": "Guard", "facing", "kind"}`) become critters made with the program's class after the setup (`Guard(x, y)`); a missing class gives a plain critter that stands still and a kind note; bad objects (outside, on the start, on a rock, twice on one square, a bad class name) are refused when the game loads
- [x] World editor on the game page (2D): ground, stone, item, water, tree, start, object (with its class name), wider/narrower/taller/shorter; every change is checked by the engine (`POST /api/game/preview`) and a bad one is undone with the reason. Editing a bundled game makes the child's own copy (✏️ in its title)
- [x] Building with code: `build.block(x, y, "stone" | "water" | "tree" | "ice" | "bridge")`, `build.clear`, `build.item`, `build.what`; at most 2,000 changes a game; never on an animal or a critter (a note instead); `tile` events and walls in every state, so the 2D board and the 3D stage redraw. In games `build` is the builder, so the beaver's own `build` trick isn't available there
- [x] Share links: `game.html#play=...` carries the game file, the code and the design card (`share.js`, nothing uploaded)
- [x] Class sharing: share kind `game` (checked with `GameSpec.from_dict`, a design card of short texts); the teacher's screen shows the design card and the code, "On the projector" has "Play this game"; children see approved games under "Games from the class" on the game page (and in the class gallery on the main page)
- [x] Doors, switches and power-ups as objects of their own (Nov 25, 2026, after G3): `{"type": "door", "name": "gate", "open": false}`, `{"type": "switch", "door": "gate"}`, `{"type": "power"}`. A closed door blocks the animal and critters like a stone (but is drawn as a door); stepping on a switch flips it, opens or closes its doors and calls `on_switch(name)`; a power-up is used up and calls `on_power()`, or without one freezes the critters for 20 ticks. Programs use `door("gate").open()`, `.close()`, `.toggle()`, `.is_open()`; a door never closes on someone. Building over one removes it. The world editor has Door, Switch and Power-up brushes; the flat board draws 🚪 (faded when open), 🔘/🟢 and 💫, the 3D stage a gate that sinks when it opens, a lever plate and a spinning star. The playtest bot counts doors as passable for "no one can reach" and walks to a switch when it is stuck. "The ghost maze" now has a gate on a shortcut, its switch and a power-up
- [ ] Not built: editing in 3D
- [ ] Gate: a class plays each other's games on the projector

*G3 Play together in class (built Nov 25, 2026)*

- [x] `gamerooms.py`: `MultiGame`, a game with one animal per player. Before a player's handlers run, that player's animal is put into the world, so `go()`, `grab()`, `where()`, `on_item` and `on_touch` act on it; `player()` says which one and `animals()` where all are. One `on_tick` and the critters once per tick; a team score; with the `caught` rule a caught animal goes back to its start (and `lose()` still ends the game for everyone). Start squares: the world's start, then the nearest open squares
- [x] Input lockstep on the deterministic engine: keys wait in the room, each tick takes up to 4 per player in joining order; `multi_inputs` records them and `replay()` gives the same game. Test: 4 players, 4,000 ticks (10 minutes at 150 ms), the replay matches the checksum of every tick
- [x] Rooms (`Room`, `Rooms`; at most 4 players, 12 rooms, closed after 10 idle minutes): open with your game and code, join from the list, only the opener starts, a room ticks by itself on the hub (a thread, 150 ms), leave anytime. API `GET /api/rooms`, `POST /api/room/open | join | start | keys | react | leave`
- [x] Push updates: `GET /api/room/events` streams every tick as server-sent events (whole state in each message, so a device that missed one draws the next; a device that stops reading is dropped and catches up when its browser reconnects). An EventSource can't send headers, so the hub takes the class code as `?code=` there only
- [x] No chat: `POST /api/room/react` takes one of six emoji, which float up on everyone's stage
- [x] On the hub: only the class's players open or join; "Pause everyone" stops every room's clock and refuses keys; ending the class closes the rooms. The offline build has no rooms
- [x] Checked in the browser on a hub with two children on two devices (two origins): open, join, start, both screens at the same tick with the same squares, keys from the second device, an emoji, pause and resume; sharing a game, the teacher's approval and projector, the classmate playing it
- [x] The 3D stage with several animals (Nov 25, 2026, after G3): each player's own animal model, standing on a ring in its player's colour (yours a little bigger); shared worlds open in the view the child picked, like a game alone. Checked: a shared world runs on the 3D stage on two devices without errors; not yet looked at on screen
- [ ] Not built: a teacher's view of all rooms, joining a game that has started
- [ ] Not checked: school Wi-Fi with 30 devices and their event streams, the cheapest tablet
- [ ] Gate: 4 children play one world without desyncs for 10 minutes

**Debugger (built Nov 25, 2026, after G3)**

Children see what their variables hold, step by step, two ways that can be used together. Both are hidden in Cub mode (the console pane is too).

- [x] 🐞 switches (`setupDebugSwitches` in `web/debug.js`, all off by default, kept in this browser as `codezoo.debug`): one beside 🎵 in the top bar turns debugging on or off in all panes at once (anything on → all off, otherwise all on; it looks pressed while any pane is on), and one in each pane's title turns on just that pane: **Blocks** line numbers on the blocks, **Python** values beside the code, **Console** the Variables bar. They replace the first version's "show values" and "variables" checkboxes. The Python pane's "let me type" checkbox became a ✏️ switch of the same kind (its words are the tooltip). Like 🎵 / 🔇, a switch that is on shows its icon in full colour and one that is off is faded with a red slash across it. The step arrow ▶ is always there, debugging or not (it replaced Blockly's highlight). Hidden in Cub mode

- [x] Engine: `Runner(watch=True)` (and `run_level(..., watch=True)`, which the web server's `/api/run` uses) gives every step a `scope` with only what changed since the step before: `g` new or changed values in the program's file scope, `g-` names that are gone, `f` the calls running now whenever they change (then `l` is all of the newest call's variables), otherwise `l` / `l-` its changes. A long run stays small. Values are Python text (`'Rex'`, `[1, 2, ...]`) cut at 60 characters, at most 30 names a scope; functions, classes, modules and `_names` are left out; an object of the learner's own class shows its attributes (`Dog(name='Rex', age=3)`) without running any of its code. Off by default, so `levels validate`, the CLI and game mode pay nothing
- [x] Option 1, the Variables bar (`web/debug.js`, under the console; the Console's 🐞): "step 9 of 12", ◀ step back (replays to the step before, with the stage, console and call stack) and ▶ step on, what the last step did ("line 3: total = 7", an error marked ⚠), the calls running now (`main → add()`), a table for the newest call's variables and one for the file's; rows that just changed are highlighted
- [x] Better view of a step, as in an IDE's debugger: one arrow ▶ beside the line number, on the filled line, which is the line that **runs next**; the stage, the console and the values show what the lines before it did (on `a = a + 1`, `a` still holds the old value). The bar says it in words ("line 4 ran: a = 2", "▶ next: line 5"). After an error the fill and ▶ turn red and stay on the line that broke; when the run ends they go away. *Changed Nov 25, 2026: the first version filled the line that had just run (with a faint mark on the one before, then a second arrow for the next line); `a = 2` on `a = a + 1` read as "not run yet", and two arrows were confusing*
- [x] Blocks: each statement block shows its code line number on its left (the Blocks pane's 🐞), and always the same ▶ (its number framed) on the block that runs next, in an HTML layer over the workspace that follows scrolling, zooming and changes and hides while a block is dragged. The block keeps its colour (Blockly's own highlight, which made it pale, is no longer used). A value block (a number, `a + 1`) counts as the statement it sits in. Programs now start a little further right to leave room for the numbers; in Cub mode only the arrow shows
- [x] Option 2, values beside the code (the Python pane's 🐞): after each line that ran, the newest values it set (`fish = 2`, `i = 1`) or what a test or `return` gave (`→ True`); the line that just ran is drawn stronger. They move with scrolling and zoom
- [x] English and Slovak; tests in `tests/test_debugger.py` (changes only, deleted names, calls and recursion, what is left out, objects, long values, error steps, the server, the page). Checked in the browser: stepping, step back twice in a row, a whole run, an error
- [ ] Not built: the debugger on the game page (game mode has "Which handler fired?"), watching an expression of the child's own, breakpoints (run to this line), values per lane for threads and tasks, read aloud of the bar, a debugger level type ("what does `x` hold after line 4?")
- [ ] Not checked: phone layout (the console is its own tab), a tablet, a real child using it
- [ ] Gate: in a pilot, children on debugging levels open the Variables bar or "show values" without being told and fix the bug faster than without it

**Block and command gallery (first version built Nov 25, 2026)**

A picture book of everything the child can use: what a block is called, what it looks like, what it does, and the Python it becomes. It answers "which block is `while`?", "what does `slide()` do?" and "how do I write this block in code?" without leaving the level.

*Decision: one gallery, opened from both panes.* Two galleries (blocks in the Blocks pane, commands in the Python pane) would have to show the same entries twice and keep them in step; one gallery whose every card shows the block **and** its code next to each other reflects them in each other by design, and a child moving from blocks to code learns from the pairing itself. The pane it was opened from only decides which side leads.

- [x] Opening: 📖 in the Blocks title and in the Python title (beside 🐞), both opening the same dialog (`web/gallery.js`, `<dialog id="block-gallery">`; closed with Esc, ✕ or a tap outside). From Blocks the card shows the block first and the code under it; from Python the code first. From Blocks it opens at the selected block; from Python at the word under the cursor (`while`, `step`, `append`)
- [x] A card: the block drawn by Blockly exactly as in the palette (one small read-only workspace, `createPreview` in `blocks.js`, as tall as the block), its Python, and the meaning from the block's own tooltip, in the child's language. The list shows each entry as a chip in its block colour with its words (an empty socket shows as "…") and the first line of its code
- [x] The two sides always match: both come from the palette entry itself (`galleryEntries` in `blocks.js` builds every entry in an invisible workspace and turns it into IR with the same code as the program, with the animal's command names: the penguin's `catch`), and the code is printed by the engine (`/api/print`, all entries in one program, cut apart by the source map). A loop or an `if` is shown with a small example inside (`for i in range(3): step(1)`, `while not is_blocked(): step(1)`, `if item_here(): grab()`, `if is_blocked(): turn_left() else: step(1)`), because an empty one prints as `if False: pass` and loses its `else`
- [x] Groups in the block families' colours (moving, actions, the animal's tricks, saying and printing, loops, questions and choices, looking around, variables, numbers, text, lists, own commands, errors, notes), and a search box that finds by block words, Python, meaning and group, in English and Slovak
- [x] What is unlocked: "In this level" first, then "🔒 Later" (faded, can be looked at but not used); other animals' tricks are left out
- [x] "Use it": "➕ Add it to my program" adds the block (with its example) at the end of the program; with ✏️ typing on, "✏️ Write it in my code" puts the code at the cursor, indented like the line it goes into. A value block (a number, `a + 1`) can only be written into code, and the card says why
- [x] Hidden in Cub mode; on a phone the list sits above the card and the dialog fills the screen
- [x] Tests: `tests/test_gallery.py` (one dialog opened from both panes, the class gallery keeps its own `#gallery`, the code side comes from the engine, every example is a palette entry of the same block, the example code is exactly what the printer prints, Slovak for the groups). Checked in the browser: both panes, the word under the cursor, search, adding a block, writing code inside a loop, the examples, a phone
- [ ] Not built yet: "unlocks in module N" (today only "Later"), a long press on a block in the program or the palette to open its card, examples for the other blocks with room inside (`for … in`, `def`, `try`, `class`), the example playing once with the debugger's ▶ and values, read aloud of a card, Cub mode's picture-only gallery, the teacher's printable sheet per module, a test that runs the gallery's blocks through the printer for every animal (today the JS side is checked in the browser)
- [ ] Gate: in a pilot, children look a block or command up in the gallery without being told, and children who switch to typing use it to find the Python for a block they know

## Not yet covered

Eleven topics still need a decision; none blocks phase 0, but each should be settled by the phase shown.

| Topic | What to decide or build | Decide by |
| --- | --- | --- |
| Proving learning | Short concept checks before and after each module; track repeated mistakes; publish pilot results for schools | Phase 1 gate |
| Curriculum fit | Map modules to the Slovak informatics curriculum, UK computing curriculum and US CSTA standards; short lesson plans for teachers | Phase 2 |
| Language of keywords | Python keywords stay English (`for`, `if`); add a translated tooltip per keyword, possibly a translated-keyword view in Cub mode | Phase 1 |
| Low-end devices | Performance budget for three.js (frame rate, bundle size) and for Pyodide start-up, a low-detail graphics setting, testing on the cheapest target tablet and Chromebook | Phase 2 |
| Installing for families | Pilot install path (`uvx`, a small installer, or a hosted page) for parents who have never used a terminal | Phase 2 |
| AI helper | No AI at launch, or a tightly limited hint-only helper; weigh child safety, cost and offline use | Phase 2 |
| Graduation path | Export as a real `.py` file and run it in normal Python; module 15 is the "first real project" and needs the real-Python mode (CPython subprocess locally, Pyodide in the browser) | Phase 3 |
| Team and budget | Confirm the roadmap's team assumption (2 developers, a content designer, a part-time artist, an education specialist); add a sound designer; cost per phase | Before phase 0 |
| Accessibility | Screen-reader support for blocks (Blockly's keyboard navigation is a start), a dyslexia-friendly font option, reduced motion and adjustable animation speed, a large-target mode for motor difficulties | Phase 2 |
| Narration cost | Speech synthesis first; record voices only for English and Slovak; budget per extra language | Phase 2 |
| Name and identity | Apache-2.0 gives no rights to the name (section 6), but that only protects a name we own. Search for "CodeZoo" / "Code Zoo" in software and education (TMview, EUIPO eSearch, ÚPV SR) before more work goes into the name; if it's clear, register an EU trade mark (classes 9, 41, maybe 42) and add the logo once there is one. Add `TRADEMARKS.md`: schools, clubs and teachers may say they use CodeZoo, unchanged copies keep the name, changed forks must rename, "based on CodeZoo" is welcome. Ask an IP attorney to check the search and classes. Keep visual design and mechanics clearly distinct from CodeMonkey | Search now (before the first pilot); registration and `TRADEMARKS.md` before any public release |

## Future improvements (to discuss later)

Valid points parked so the work can focus on the MVP. None of them blocks phases 0–1; pick each up at the "revisit" point and turn it into plan changes then.

### 1. Team: one developer plus a coding agent

The roadmap assumes two developers, but the real setup is one developer working with Claude Code. That speeds up writing code; it does not remove the risks, it moves them:

- **Review time becomes the bottleneck.** Code arrives faster than one person can check it, so the scope risk becomes "more output than can be verified". Small changes, tests and CI on every step keep this manageable.
- **Pilots stay human work.** Recruiting families, watching an 8-year-old get stuck and testing on real tablets cannot be delegated to the agent.
- **The agent has no memory between sessions** except what is written down. This plan, `SPEC.md` files, tests and CI are what keep it consistent over months.
- **The interpreter risk is about scope, not typing speed.** Every Python feature adds behaviour to test and ways to differ from CPython; the documented subset per module still applies.

**To discuss:** rewrite the team assumption as "one developer + coding agent", with the developer's hours per week as the real limit, and re-estimate each phase from that.
**Revisit:** at the phase 0 gate, using how long phase 0 actually took.

### 2. Accessibility and narration cost

**Accessibility.** The design assumes children who can drag precisely, see colours and enjoy motion. Others need:

| Group | Needs |
| --- | --- |
| Blind and low-vision children | Screen reader reads blocks and code; keyboard-only moving and placing of blocks (a main reason for the Blockly spike, which already has keyboard navigation) |
| Dyslexic children | Font choice, larger text and line spacing in the code pane |
| Motion sensitivity, epilepsy, attention difficulties | "Reduced motion" setting (fewer glows, slides and wiggles, especially in Cub mode); adjustable animation speed |
| Motor difficulties | Large tap targets, tap-to-place instead of precise drag, no time pressure |

Accessibility is cheaper to design in than to add later, and schools increasingly require it for learning tools.

**Narration cost.** Cub mode reads everything aloud for children who cannot read yet:

| Option | For | Against |
| --- | --- | --- |
| Browser speech synthesis | Free, instant, many languages | Robotic; quality varies by device; Slovak voices may be weak or missing; mispronounces names and code words |
| Recorded voices | Warm, much better for small children | Every block, hint and story line recorded per language; every wording change means another session; voice actor, studio and editing costs |

Cost grows with languages × amount of text and keeps growing as content changes. Current plan: speech synthesis first, recorded voices only for English and Slovak, each extra language budgeted separately.

**To discuss:** which accessibility features are in the MVP; whether to record any voices before Cub mode is confirmed.
**Revisit:** at the phase 1 gate (Blockly and Cub mode decisions).

### 3. Free or paid, open or closed

The phase 2 pilot is when real families start using CodeZoo, and the money model changes what is built and what they are told:

- **Promises to families.** Pilot parents will ask whether it stays free; charging later for something promised free loses the trust a children's app depends on.
- **Accounts and privacy.** Paid usually means a purchase or licence check and often accounts, which brings parental consent, GDPR and COPPA work and a server. "Everything stays on the device" fully holds only for free or one-time-purchase models.
- **Open source.** Invites community animal packs and teacher forks, which the plan wants, but makes selling harder; the code moved from MIT to Apache-2.0 on Nov 20, 2026 (same freedom to use, fork and sell, plus an explicit patent grant and a NOTICE file); copies already shared under MIT stay MIT.
- **Schools.** Paid school licences would pull the teacher class view (phase 5) much earlier.

| Option | Fits the current plan? |
| --- | --- |
| Free and open source, funded by grants or donations | Yes, no changes |
| Free app, paid school licences | Mostly; teacher view and some accounts move earlier |
| One-time purchase, no account | Yes for privacy; app stores take a share; harder to keep open source |
| Subscription | Least; needs accounts, server and billing |

**Decided (Nov 21, 2026): free and open source.** CodeZoo stays free for children and adults, under Apache-2.0, with no accounts, ads or purchases. Support comes from voluntary donations through Buy Me a Coffee ([buymeacoffee.com/mse11](https://buymeacoffee.com/mse11)). Donations are optional and unlock nothing: every feature stays free for everyone.

**Where the donation link may appear.** Only where grown-ups are: the README ("Support" section), the project page, the Grown-ups area in the game (behind the gate, under "Support CodeZoo") and the teacher's screen of a classroom hub. Never on a child's screen: not on the stage, after a run, in "My zoo", the class gallery, the join screen or the goodbye screen. Kid-safety seals forbid payment prompts aimed at children, and a child tapping a payment link by accident breaks the "no purchases" promise. The link opens the page in a new tab and sends nothing about the player. `tests/test_web_support.py` checks that the link appears only in those places.

Paid work for schools that want a special programme (custom levels, a workshop, curriculum mapping) stays possible later as a service around the open code, not as locked features.

**Promise to pilot families:** "CodeZoo is free and open source and will stay free. It needs no account, and your child's progress stays on your device."

### 4. Game mode: children make their own games

Platforms like Roblox show how much children want to build worlds, script how things behave and play each other's creations. CodeZoo already has most of the pieces: the level editor, share links, class sharing with the teacher's approval, outfits, the 3D stage, the classroom hub and a deterministic engine with a clock. What is missing is the paradigm: today a program *solves* a puzzle and runs to the end; in game mode a program *writes the rules* of a world that someone then plays live.

**Pitch:** make games together, in your classroom, with no strangers and no cloud.

| Platform piece | CodeZoo today | Gap |
| --- | --- | --- |
| Build a world | Level editor paints worlds, goals and files | Objects that do things: doors, switches, critters, power-ups |
| Script behaviour | One-shot solution on a simulated clock | Event handlers that react while someone plays |
| Others play it | Share links, "Share with the class", projector | Mostly there |
| Avatars | Animals, outfits, stickers | Mostly there |
| Play together live | Classroom hub, but everyone plays alone | Real-time sync over the local network |
| Public platform, chat, marketplace | Nothing, on purpose | **Not built**: strangers, chat moderation and payment pressure on children go against the privacy promise and are too much for one developer |

**What a game program looks like.** The same Python subset, plus a few event hooks (as built in G0, see "Phase 8 steps"):

```python
class Guard(Critter):
    def on_tick(self):
        if self.wall_ahead():
            self.turn_around()
        else:
            self.step()

guard = Guard(0, 2, "east")

def on_key(key):          # "up", "down", "left", "right", "space"
    go(key)

def on_item(item):        # the animal arrived on an item: "banana"
    grab()
    score.add(1)

def on_touch(critter):    # a critter and the animal met
    lose("Caught!")
```

Events, callbacks and game loops give modules 7 (functions) and 12 (objects) a reason to exist: `class Guard(Critter)` is the best excuse to learn inheritance. The program runs once to set up (functions, classes, critters); then the game calls its handlers on every tick, with a budget of interpreter steps per tick.

**Ideas from vibe game development**, applied to children as game designers rather than to how CodeZoo is built (see [Lessons from vibe game development](#lessons-from-vibe-game-development) for that):

| What the article showed | Game mode idea |
| --- | --- |
| "Make it a LOT more fun" worked because the agent ran 1,000+ simulated games and balanced them | **"Test my game" playtest bot.** Bot animals play the child's game a few hundred times on the simulated clock and report in kind words: "Nobody could win: the guard is too fast", "Every bot won in 3 steps: too easy?", "No one can reach the key". Builds on the editor's "Test the level"; teaches balance and iteration |
| Grow a game in small rounds, one visible change per turn | **Lessons in rounds:** move with keys (`on_key`) → one thing to collect and a score → a guard that walks (`on_tick`) → the guard catches you (`on_touch`) → "make it more fun": pick one twist card (speed-up, secret door, power-up). Each round is one run with a visible result, like predict–fix–make in Cub mode |
| Tight single-mechanic loops balance better than complex systems | **Four templates first:** collect, dodge, chase, maze, each with one core rule. No crafting, shops or quests at first. Templates also prevent the blank-page freeze |
| Spec and critique before building | **Design card:** "My game in one sentence", "How do I win?", "How do I lose?". The teacher can approve it before building, like sharing |
| Most fixing went into global-state bugs | **State bugs become lessons:** debugging levels where two handlers fight over `score` or move the same guard; the burrows and lanes view shows which handler fired on each tick and what it changed |
| Floating-point results differ across platforms and break replays and multiplayer | **Integer-only game state:** positions on the grid, time in ticks; floats only for drawing in three.js. A CI test runs one game in CPython and Pyodide and compares the event logs |
| 3D models built in code | **Building with code:** `for x in range(5): build.block(x, 0, "stone")`. Loops make walls, functions make houses, recursion makes trees: a creative mode that is also the curriculum |
| Music synthesised in code that reacts to the game | **Game-state sound** with WebAudio, no asset files; children can script it (`music.tempo = 120` when a guard is near) |
| A sync feature worked but gave a player a headache | **Comfort limits:** volume cap, no harsh high pitches, a flash limit, and the existing "less motion" setting applies to games |

**Proposed steps**

| Step | Deliverable | Gate |
| --- | --- | --- |
| G0 Spike | Real-time ticks and `on_tick` / `on_key` / `on_touch` in the interpreter; one hand-made game playable with keys and touch, 2D and 3D; ticks-per-second and playtest-bot timings measured (see below) | Runs smoothly on the cheapest target tablet (2D at least); the measurements decide the language question below |
| G1 Make a game, alone | Event API, `Critter` base class, score and win/lose rules, the four templates, the lesson rounds, design card, "Test my game" bot | 5 children make and finish a game in one session and want to make another |
| G2 Game editor and sharing | Level editor places objects with attached scripts; games travel in share links and through class sharing with the teacher's approval; building with code | A class plays each other's games on the projector |
| G3 Play together in class | Several animals in one world over the hub, input lockstep on the deterministic engine, push updates (server-sent events or websockets); no chat, only emoji reactions | 4 children play one world without desyncs for 10 minutes |

**G0: language and performance.** Is a game engine in Python naive? No, as long as the engine and the children's scripts stay separate, the way large platforms run a native engine with a scripting language on top. CodeZoo already splits it this way:

| Layer | What it does | Language | Must be fast? |
| --- | --- | --- | --- |
| Drawing, animation, input, sound | 60 frames a second, smooth movement between ticks | JS + three.js | Yes, and it already is |
| Game rules | The child's `on_tick`, `on_touch`, `on_key` | CodeZoo's interpreter (Python) | Only 5–10 ticks a second on a grid |
| Children's language | What they write | Python | It is the product; it doesn't change |

The interpreter (`interpreter.py`, `Runner.run_steps`) walks the IR tree and yields a `Step` per statement. In the browser it runs on Pyodide, so it is an interpreter on an interpreter, roughly 50–100× slower than native CPython (an estimate, to be measured). A tick with a few critters is a few hundred to a few thousand steps, which should fit at 5–10 ticks a second. The real risk is the playtest bot: 300 games × 200 ticks is 60,000 ticks and could take minutes on a cheap tablet. So it runs on the classroom hub in native CPython where there is one, runs fewer games in the browser (30 are enough to say "nobody could win"), and runs in the existing web worker so the page stays responsive.

Switching language costs more than it saves:

| Option | Gain | Loss |
| --- | --- | --- |
| Rewrite the interpreter in JS/TypeScript | Faster in the browser, no Pyodide | One engine for CLI, terminal game, tests and browser; differential tests against CPython in the same pytest run; months of rework of every phase 2–4 feature |
| Rust compiled to WebAssembly | Very fast | Same, plus a toolchain one developer must maintain |
| Skulpt, Brython or MicroPython | Ready-made | Stepping, the seeded scheduler, source maps and the simulated clock: what makes CodeZoo special |
| Children's code straight in Pyodide's CPython | Fast | No stepping, line highlighting, limits or deterministic replays |

The interpreter's value is control (stepping, highlighting, deterministic concurrency, kind errors, limits), not speed. Decisions:

1. **Keep Python.** G0 measures ticks per second with 5 critters on the cheapest target tablet in Pyodide, and how long 30 and 300 playtest-bot games take in the browser and on the hub. *Measured on a desktop (Nov 24, 2026): about 1,100 ticks a second in Pyodide, 3,000 in CPython, against 7 needed; the tablet is still to measure. See "Phase 8 steps".*
2. **Optimize before rewriting.** If ticks are too slow, compile the IR once into Python closures instead of walking the tree on every step (often several times faster, same behaviour and tests), and profile the hot paths.
3. **Keep the fallback open without building it.** The IR and `codezoo schema` are already a contract; a JS or WebAssembly interpreter could run the same IR later, with the Python interpreter as the reference it is tested against. Only real G0 numbers can trigger that.
4. **Design game mode for an interpreter:** grid positions and ticks, no physics simulation, and a step budget per tick, so a runaway `while True` in a handler ends with a kind message ("the guard got tired") instead of freezing the game.

**Risks.** Scope: G3 alone may take as long as several earlier phases. Focus: free-form games can drift away from learning Python, so game levels keep goals and stars ("make the guard patrol and catch the fox"). Speed: a real-time 3D loop on old tablets probably needs the 2D stage as the default for games. Name and look: keep the mechanics generic and the visual design CodeZoo's own; never copy another platform's names, art or worlds.

**To discuss:** whether game mode comes before more curriculum content; which template is the first one; whether G3 is worth its cost or class sharing (G2) is enough.
**Revisit:** after the first real pilot returns its metrics.
