"""The ``codezoo`` command line. The only module that imports click."""

from __future__ import annotations

import functools
import json
import sys
import time
from pathlib import Path
from typing import Any

import click

from mse_codezoo import __version__, ir
from mse_codezoo.game import (
    LevelRun,
    attempt_from_run,
    level_to_json,
    run_level,
    run_to_json,
    skipped_reason,
    solution_errors,
)
from mse_codezoo.i18n import LANGS, use_lang
from mse_codezoo.interpreter import Step
from mse_codezoo.lang_python import ParseResult, block_label, outline, parse, print_program
from mse_codezoo.levels import (
    LEVELS_DIR,
    Level,
    LevelError,
    find_level,
    level_files,
    load_level,
    load_pack,
    solution_path,
    validate_level,
)
from mse_codezoo.profiles import MAX_NAME, PICTURES, ProfileError, ProfileStore
from mse_codezoo.versions import RELEASES, parse_version, version_text
from mse_codezoo.world import World

ProgramPath = click.Path(exists=True, dir_okay=False, path_type=Path)
PYTHON_CHOICES = click.Choice([version_text(v) for v in RELEASES])


def python_option(fn: Any) -> Any:
    return click.option(
        "--python",
        "python",
        type=PYTHON_CHOICES,
        help="The Python release the program is written for (default: the newest this "
        "computer can read). Newer syntax is refused with the release that brought it.",
    )(fn)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="codezoo")
@click.option(
    "--lang",
    type=click.Choice(LANGS),
    envvar="CODEZOO_LANG",
    help="Language for messages, titles and hints (or set CODEZOO_LANG).",
)
@click.pass_context
def main(ctx: click.Context, lang: str | None) -> None:
    """CodeZoo: learn real Python through animal coding games."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")  # a console that can't show "č" shows "?"
            except (ValueError, OSError):
                pass
    ctx.with_resource(use_lang(lang))


# --- helpers -------------------------------------------------------------------


def own_modules(program: Path, source: str) -> dict[str, str]:
    """Helper files the program imports that sit next to it, like your own ``tricks.py``."""
    parsed = parse(source)
    if parsed.program is None:
        return {}
    found = {}
    for node in ir.walk(parsed.program):
        if isinstance(node, ir.Import):
            path = program.with_name(f"{node.module}.py")
            if path.is_file() and path.resolve() != program.resolve():
                found[node.module] = path.read_text(encoding="utf-8")
    return found


def _all_levels() -> list[Level]:
    return [load_level(path) for path in level_files()]


def _load(level_ref: str, program: Path) -> tuple[Level, str]:
    try:
        level = find_level(level_ref)
    except LevelError as exc:
        raise click.ClickException(str(exc)) from None
    return level, program.read_text(encoding="utf-8")


def _echo_diagnostics(parsed: ParseResult) -> None:
    for d in parsed.diagnostics:
        label = "error" if d.severity == "error" else "note"
        click.echo(f"line {d.line}: {label}: {d.message}", err=d.severity == "error")


def describe_event(event: dict[str, Any], world: World) -> str:
    match event["type"]:
        case "move":
            x, y = event["to"]
            return f"moved to ({x}, {y})"
        case "turn":
            return f"now facing {event['facing']}"
        case "grab":
            item = event["item"]
            if item:
                return f"grabbed a {world.pack.item_name(item)}"
            if event.get("near", "none") != "none":
                where = event["near"]
                target = world.pack.item_name(event.get("target"))
                return f"nothing to grab here (the {target} is {where}, {event['distance']} away)"
            return "nothing to grab here"
        case "say":
            return f'says "{event["text"]}"'
        case "bump":
            return "bump!"
        case "sense":
            return f"asks {event['what']}() -> {event['result']!r}"
        case "swing":
            x, y = event["to"]
            return f"swung across to ({x}, {y})"
        case "climb":
            item = event.get("item")
            return f"climbed a tree, got a {world.pack.item_name(item)}" if item else "climbed"
        case "crack":
            return "crack! thin ice ahead"
        case "build":
            return f"built a {world.pack.item_name(event['item'])} log into the dam"
        case "hide":
            return "hides"
        case "call":
            return f"calls {event['name']}({', '.join(event['args'])})"
        case "return":
            return f"{event['name']} gives back {event['value']}"
    return event["type"]


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _short_path(path: Path) -> str:
    """Path relative to the bundled levels folder (or the parent folder) for messages."""
    try:
        return path.resolve().relative_to(LEVELS_DIR.resolve()).as_posix()
    except ValueError:
        return f"{path.parent.name}/{path.name}"


def _level_header(level: Level, animal: str | None) -> str:
    return f"Level {level.id}: {level.title_for(animal)} ({animal or level.animal})"


# --- run / check / blocks ----------------------------------------------------------


@main.command()
@click.argument("level")
@click.argument("program", type=ProgramPath)
@click.option("--animal", help="Play as another animal (default: the level's animal).")
@click.option("--trace", is_flag=True, help="Print every step and the grid after each move.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable output.")
@click.option(
    "--save",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Save the run as a .run.json file, for `codezoo replay` and `codezoo story export`.",
)
@python_option
def run(
    level: str,
    program: Path,
    animal: str | None,
    trace: bool,
    as_json: bool,
    save: Path | None,
    python: str | None,
) -> None:
    """Run PROGRAM headless in LEVEL (a level id like m01-l01, or a level file).

    PROGRAM may `import` your own helper files that sit next to it (like tricks.py).
    """
    lvl, source = _load(level, program)
    source_lines = source.splitlines()

    def on_step(step: Step, world: World, parsed: ParseResult) -> None:
        span = parsed.positions.get(step.node_id)
        line = span.line if span else 0
        code = source_lines[line - 1].strip() if 0 < line <= len(source_lines) else ""
        click.echo(f"{line:>4} | {code}")
        for event in step.events:
            click.echo(f"     |   {describe_event(event, world)}")
        if step.note:
            click.echo(f"     |   {step.note}")
        if step.lane and step.lane != "main":
            click.echo(f"     |   [{step.lane} @ {step.time:g}]")
        if any(e["type"] in ("move", "turn", "grab") for e in step.events):
            click.echo(_indent(world.render()))

    if not as_json:
        click.echo(_level_header(lvl, animal))
    try:
        result = run_level(
            lvl,
            source,
            animal=animal,
            on_step=on_step if trace else None,
            modules=own_modules(program, source),
            python=parse_version(python),
        )
    except LevelError as exc:
        raise click.ClickException(str(exc)) from None

    if save is not None and result.result is not None:
        from mse_codezoo.runs import make_run

        save.write_text(json.dumps(make_run(result, source), indent=1), encoding="utf-8")
        if not as_json:
            click.echo(f"Saved the run to {save}")
    if as_json:
        click.echo(json.dumps(run_to_json(result), indent=2))
    else:
        _echo_run(result, show_grid=not trace)
    if not result.parsed.ok or (result.result and result.result.error):
        raise SystemExit(1)


def _echo_run(run: LevelRun, show_grid: bool) -> None:
    _echo_diagnostics(run.parsed)
    if run.result is None or run.world is None:
        return
    if show_grid:
        click.echo(_indent(run.world.render()))
    for line in run.result.output:
        click.echo(f"printed: {line}")
    if run.result.error:
        error = run.result.error
        if len(error.traceback) > 1:
            click.echo("Traceback (where it happened, from the outside in):", err=True)
            frames = error.traceback
            if len(frames) > 6:  # deep recursion: the start and the end tell the story
                frames = [*frames[:3], ("...", f"{len(frames) - 5} more"), *frames[-2:]]
            for name, node in frames:
                if name == "...":
                    click.echo(f"  ... {node} ...", err=True)
                    continue
                where = "the program" if name == "<program>" else f"{name}()"
                click.echo(f"  line {run.line_of(node)}, in {where}", err=True)
        line = run.line_of(error.node_id)
        click.echo(f"line {line}: {error.message}", err=True)
    else:
        click.echo(f"Finished in {len(run.result.steps)} steps.")
    if run.result.lanes:
        lanes = ", ".join(lane for lane in run.result.lanes if lane != "main")
        click.echo(f"Ran at the same time: {lanes}; done by tick {run.result.time:g}.")


@main.command()
@click.argument("level")
@click.argument("program", type=ProgramPath)
@click.option("--animal", help="Play as another animal (default: the level's animal).")
@click.option("--profile", "player", help="Save the result to this player's progress.")
@python_option
def check(
    level: str, program: Path, animal: str | None, player: str | None, python: str | None
) -> None:
    """Check PROGRAM against LEVEL's goal and constraints; print stars and hints."""
    lvl, source = _load(level, program)
    try:
        result = run_level(
            lvl,
            source,
            animal=animal,
            modules=own_modules(program, source),
            python=parse_version(python),
        )
    except LevelError as exc:
        raise click.ClickException(str(exc)) from None
    extras: list[str] = []
    if player is not None:
        try:
            extras = _after_attempt(_store(), player, lvl, result, source)
        except ProfileError as exc:
            raise click.ClickException(str(exc)) from None
    click.echo(_level_header(lvl, animal))
    _echo_diagnostics(result.parsed)
    if result.check is None:
        raise SystemExit(1)
    outcome = result.check
    line = result.line_of(result.result.error.node_id) if result.result.error else None
    click.echo(f"line {line}: {outcome.message}" if line else outcome.message)
    click.echo(f"Stars: {outcome.earned}/{len(outcome.stars)}")
    for star in outcome.stars:
        click.echo(f"  [{'x' if star.earned else ' '}] {star.label}")
    if result.feeling is not None:
        click.echo(result.feeling.text)
    if not outcome.solved and lvl.shown_hints:
        click.echo(f"Hint: {lvl.shown_hints[0]}")
    for line in extras:
        click.echo(line)
    if not outcome.solved:
        raise SystemExit(1)


def _after_attempt(
    store: ProfileStore, player: str, level: Level, result: LevelRun, source: str
) -> list[str]:
    """Record the attempt; lines about new stickers and a practice suggestion."""
    store.record(player, attempt_from_run(result, source))
    levels = _all_levels()
    solved = result.check is not None and result.check.solved
    new = store.award(player, levels) if solved else []  # stickers only with a solved run
    lines = [f"New sticker: {s['emoji']} {s['name']}" for s in new]
    suggestion = store.suggest(player, level, levels)
    if suggestion:
        lines.append(
            f"Want some practice with {suggestion['concept']} first? "
            f"Try {suggestion['level']}: {suggestion['title']}"
        )
    return lines


@main.command()
@click.argument("program", type=ProgramPath)
def blocks(program: Path) -> None:
    """Print PROGRAM as a block outline with each block's lines and node id."""
    parsed = parse(program.read_text(encoding="utf-8"))
    _echo_diagnostics(parsed)
    if not parsed.ok or parsed.program is None:
        raise SystemExit(1)
    source_map = print_program(parsed.program).source_map
    for depth, stmt in outline(parsed.program):
        span = source_map[stmt.id]
        lines = f"{span.line}" if span.line == span.end_line else f"{span.line}-{span.end_line}"
        click.echo(f"{lines:>6}  {stmt.id:<5} {'    ' * depth}{block_label(stmt)}")


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Address to listen on.")
@click.option("--port", default=8765, show_default=True, help="Port to listen on (0 = any).")
@click.option("--open", "open_browser", is_flag=True, help="Open the page in a web browser.")
@click.option("--verbose", is_flag=True, help="Log every request.")
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Keep players and progress here (default: CODEZOO_HOME or the OS user-data folder).",
)
def serve(host: str, port: int, open_browser: bool, verbose: bool, data_dir: Path | None) -> None:
    """Start the local web UI: stage, blocks and code in the browser."""
    import webbrowser

    from mse_codezoo.server import CodeZooServer

    try:
        server = CodeZooServer(host, port, verbose=verbose, store=ProfileStore(data_dir))
    except OSError as exc:
        raise click.ClickException(f"cannot listen on {host}:{port}: {exc}") from None
    click.echo(f"CodeZoo is running at {server.url}  (press Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nBye!")
    finally:
        server.server_close()


PLAY_KEYS = {
    "r": "run",
    "e": "edit",
    "w": "watch",
    "h": "hint",
    "n": "next",
    "p": "previous",
    "l": "levels",
    "q": "quit",
}


def _can_show(text: str) -> bool:
    """Whether the terminal's encoding can show ``text`` (old Windows consoles can't)."""
    try:
        text.encode(getattr(sys.stdout, "encoding", None) or "utf-8")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _program_file(level: Level, folder: Path) -> Path:
    """The file the player edits for ``level``; created with the goal and starter."""
    path = folder / f"{level.id}.py"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        world = World.from_spec(level.world, load_pack(level.animal))
        header = [
            f"# Level {level.id}: {level.shown_title}",
            f"# Goal: {describe_goal(level.goal, world)}",
        ]
        if len(level.worlds()) > 1:
            header.append(f"# This level has {len(level.worlds())} worlds; solve them all.")
        header.append("# Save this file, then go back to CodeZoo and press r (or w to watch it).")
        path.write_text("\n".join(header) + "\n\n" + level.starter, encoding="utf-8")
    return path


def _play_levels(lang_levels: list[Level], player: str | None, store: ProfileStore) -> int:
    """Index of the first level the player hasn't solved yet."""
    if player is None:
        return 0
    solved = {k for k, v in store.progress(player)["levels"].items() if v.get("solved")}
    for index, level in enumerate(lang_levels):
        if level.id not in solved:
            return index
    return 0


def _show_level(level: Level, path: Path, color: bool, variant: int) -> None:
    from mse_codezoo.term import StageState, legend, render

    data = level_to_json(level)
    world = data["worlds"][variant]
    click.echo("")
    click.secho(f"Level {level.id}: {level.shown_title}", bold=True)
    goal_world = World.from_spec(level.worlds()[variant][0], load_pack(level.animal))
    click.echo(f"Goal: {describe_goal(level.worlds()[variant][1], goal_world)}")
    if len(data["worlds"]) > 1:
        click.echo(f"World {variant + 1} of {len(data['worlds'])} (the program must solve all)")
    click.echo(render(StageState.from_json(world), color=color))
    click.echo(
        legend(
            goal_world.pack,
            [tile for _x, _y, tile in world["items"]],
            [kind for _x, _y, kind in world.get("terrain", [])],
        )
    )
    click.echo(f"Your program: {path}")


@main.command()
@click.option("--level", "level_ref", help="Start at this level (default: the first unsolved).")
@click.option("--profile", "player", help="Save stars and progress for this player.")
@click.option(
    "--dir",
    "folder",
    type=click.Path(file_okay=False, path_type=Path),
    help="Folder for your program files (default: <data folder>/play).",
)
@click.option("--speed", type=click.IntRange(1, 5), default=3, show_default=True)
@click.option("--no-color", is_flag=True, help="Plain text, no colours.")
def play(
    level_ref: str | None, player: str | None, folder: Path | None, speed: int, no_color: bool
) -> None:
    """Play in the terminal: edit a .py file, run it, watch the animal on the grid.

    Each level gets its own program file. Press e to open it in your editor ($EDITOR),
    r to run it, or w to rerun it every time you save.
    """
    from mse_codezoo.term import replay

    store = _store()
    color = not no_color and sys.stdout.isatty()
    animate = sys.stdout.isatty()
    all_levels = [load_level(path) for path in level_files()]
    try:
        if player is not None:
            player = store.find(player).id
        index = _play_levels(all_levels, player, store)
        if level_ref is not None:
            wanted = find_level(level_ref).id
            index = next(i for i, lvl in enumerate(all_levels) if lvl.id == wanted)
    except (LevelError, ProfileError) as exc:
        raise click.ClickException(str(exc)) from None
    if player is not None and store.today_status(player)["over"]:
        click.echo("That's all for today! The animal is asleep. See you tomorrow.")
        return
    folder = folder or store.root / "play"
    hints_shown = 0
    variant = 0
    last_tick = time.monotonic()

    def run_once(level: Level, path: Path) -> bool:
        nonlocal last_tick
        source = path.read_text(encoding="utf-8")
        result = run_level(
            level,
            source,
            variant=variant,
            seed=int(time.time()),
            modules=own_modules(path, source),
        )
        data = run_to_json(result)
        _echo_diagnostics(result.parsed)
        if data.get("steps") is not None:
            replay(
                level_to_json(level)["worlds"][variant],
                data["steps"],
                source.splitlines(),
                echo=click.echo,
                color=color,
                animate=animate,
                speed=speed,
                header=f"Level {level.id}: {level.shown_title}",
            )
            for line in result.result.output if result.result else []:
                click.echo(f"printed: {line}")
        if result.check is not None:
            outcome = result.check
            line = result.line_of(result.result.error.node_id) if result.result.error else None
            click.echo(f"line {line}: {outcome.message}" if line else outcome.message)
            fancy = _can_show("★☆✓–")
            full, empty, yes, no = ("★", "☆", "✓", "–") if fancy else ("*", ".", "x", "-")
            stars = full * outcome.earned + empty * (len(outcome.stars) - outcome.earned)
            labels = "; ".join(f"{yes if s.earned else no} {s.label}" for s in outcome.stars)
            click.echo(f"{stars}  {labels}")
        if result.feeling is not None:
            face = result.feeling.face if _can_show(result.feeling.face) else ""
            click.echo(f"{face} {result.feeling.text}".strip())
        if player is not None:
            for line in _after_attempt(store, player, level, result, source):
                click.echo(line)
            now = time.monotonic()
            status = store.add_time(player, now - last_tick)
            last_tick = now
            if status["over"]:
                click.echo("That's all for today! The animal is going to sleep. See you tomorrow.")
                return False
        return True

    while True:
        level = all_levels[index]
        path = _program_file(level, folder)
        _show_level(level, path, color, variant)
        keys = "  ".join(f"[{key}]{name[1:]}" for key, name in PLAY_KEYS.items())
        if len(level.worlds()) > 1:
            keys += "  [1-9] world"
        choice = click.prompt(keys, default="r", show_default=False).strip().lower()[:1]
        if choice.isdigit() and 1 <= int(choice) <= len(level.worlds()):
            variant = int(choice) - 1
        elif choice == "r":
            if not run_once(level, path):
                return
        elif choice == "e":
            try:
                click.edit(filename=str(path))
            except click.ClickException as exc:
                click.echo(f"Can't open an editor ({exc.message}). Open {path} yourself.")
                continue
            if not run_once(level, path):
                return
        elif choice == "w":
            click.echo(f"Watching {path}. Save it to run again; press Ctrl+C to stop.")
            seen = path.stat().st_mtime
            try:
                while True:
                    time.sleep(0.4)
                    mtime = path.stat().st_mtime
                    if mtime != seen:
                        seen = mtime
                        if not run_once(level, path):
                            return
            except KeyboardInterrupt:
                click.echo("")
        elif choice == "h":
            hints = level.shown_hints
            if hints:
                hints_shown = min(hints_shown + 1, len(hints))
                click.echo(f"Hint {hints_shown}: {hints[hints_shown - 1]}")
            else:
                click.echo("No hints for this level.")
        elif choice in ("n", "p"):
            index = (index + (1 if choice == "n" else -1)) % len(all_levels)
            hints_shown = 0
            variant = 0
        elif choice == "l":
            for number, lvl in enumerate(all_levels, 1):
                click.echo(f"{number:>3}  {lvl.id:<9} {lvl.shown_title}")
            picked = click.prompt("Level number", type=click.IntRange(1, len(all_levels)))
            index = picked - 1
            hints_shown = 0
            variant = 0
        elif choice == "q":
            click.echo("Bye!")
            return


@main.command()
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write to this file instead of printing (e.g. mse_codezoo/ir.schema.json).",
)
def schema(output: Path | None) -> None:
    """Print the JSON Schema of the program model (IR), the contract with the web client."""
    text = json.dumps(ir.json_schema(), indent=2) + "\n"
    if output is None:
        click.echo(text, nl=False)
    else:
        output.write_text(text, encoding="utf-8", newline="\n")
        click.echo(f"wrote {output}")


# --- profiles and grown-ups -----------------------------------------------------------


def _store() -> ProfileStore:
    return ProfileStore()


def _profile_errors(fn: Any) -> Any:
    """Show ProfileError as a plain message instead of a traceback."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ProfileError as exc:
            raise click.ClickException(str(exc)) from None

    return wrapper


def _plural(n: float, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _ask_pin(store: ProfileStore) -> str | None:
    if not store.parent().has_pin:
        return None
    pin = click.prompt("Grown-up PIN", hide_input=True)
    store.check_pin(pin)
    return pin


@main.group()
def profile() -> None:
    """On-device learner profiles (no accounts, nothing leaves the computer)."""


@profile.command("list")
@_profile_errors
def profile_list() -> None:
    """List players and their stars."""
    store = _store()
    players = store.profiles()
    for p in players:
        levels = store.progress(p.id)["levels"]
        stars = sum(e.get("stars", 0) for e in levels.values())
        solved = sum(1 for e in levels.values() if e.get("solved"))
        click.echo(f"{p.name:<{MAX_NAME}}  {p.picture:<8}  {solved} levels solved, {stars} stars")
    click.echo(f"{len(players)} player(s) in {store.root}")


@profile.command("add")
@click.argument("name")
@click.option("--picture", type=click.Choice(PICTURES), default=PICTURES[0], show_default=True)
@_profile_errors
def profile_add(name: str, picture: str) -> None:
    """Add a player."""
    created = _store().add(name, picture)
    click.echo(f"Added {created.name} ({created.picture}).")


@profile.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Don't ask for confirmation.")
@_profile_errors
def profile_remove(name: str, yes: bool) -> None:
    """Remove a player and their progress (needs the grown-up PIN if one is set)."""
    store = _store()
    target = store.find(name)
    _ask_pin(store)
    if not yes:
        click.confirm(f"Remove {target.name} and all their progress?", abort=True)
    store.remove(target.id)
    click.echo(f"Removed {target.name}.")


@profile.command("export")
@click.argument("name")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True)
@_profile_errors
def profile_export(name: str, output: Path) -> None:
    """Save a player's progress to a file (for another computer, or as a backup)."""
    data = _store().export(name)
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(f"Saved {data['profile']['name']} to {output}")


@profile.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@_profile_errors
def profile_import(file: Path) -> None:
    """Load a player from a file made by `codezoo profile export`."""
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Can't read {file.name}: {exc}") from None
    created = _store().import_(data)
    click.echo(f"Imported {created.name}.")


@main.group()
def parent() -> None:
    """Grown-up settings: daily time limit, private mode, PIN, and a learning report."""


@parent.command("show")
@_profile_errors
def parent_show() -> None:
    """Show the current grown-up settings."""
    settings = _store().parent()
    limit = f"{settings.daily_minutes} minutes" if settings.daily_minutes else "none"
    click.echo(f"Daily limit:  {limit}")
    click.echo(f"Private mode: {'on' if settings.private_mode else 'off'}")
    click.echo(f"PIN:          {'set' if settings.has_pin else 'not set'}")


@parent.command("set")
@click.option("--daily-minutes", type=int, help="Daily play limit per player (0 = no limit).")
@click.option(
    "--private/--no-private",
    "private_mode",
    default=None,
    help="Private mode keeps only stars and solved levels.",
)
@_profile_errors
def parent_set(daily_minutes: int | None, private_mode: bool | None) -> None:
    """Change the daily limit or private mode."""
    store = _store()
    pin = _ask_pin(store)
    minutes: int | None | str = "keep"
    if daily_minutes is not None:
        minutes = None if daily_minutes == 0 else daily_minutes
    store.update_parent(pin=pin, daily_minutes=minutes, private_mode=private_mode)
    click.echo("Saved.")


@parent.command("pin")
@click.option("--clear", is_flag=True, help="Remove the PIN.")
@_profile_errors
def parent_pin(clear: bool) -> None:
    """Set, change or clear the grown-up PIN (4 to 8 digits)."""
    store = _store()
    pin = _ask_pin(store)
    if clear:
        store.update_parent(pin=pin, clear_pin=True)
        click.echo("PIN removed.")
        return
    new_pin = click.prompt("New PIN", hide_input=True, confirmation_prompt=True)
    store.update_parent(pin=pin, new_pin=new_pin)
    click.echo("PIN saved.")


@parent.command("report")
@click.argument("name")
@_profile_errors
def parent_report(name: str) -> None:
    """What a player has learned so far."""
    store = _store()
    _ask_pin(store)
    report = store.report(name, [load_level(path) for path in level_files()])
    who = report["profile"]
    click.echo(f"{who['name']} ({who['picture']})")
    click.echo(
        f"Solved {_plural(report['levelsSolved'], 'level')}, {_plural(report['stars'], 'star')}, "
        f"{_plural(report['minutesThisWeek'], 'minute')} in the last 7 days"
    )
    click.echo("Ideas:")
    for row in report["concepts"]:
        done = f"({row['solved']}/{row['levels']} levels)"
        click.echo(f"  {row['concept']:<10} {row['status']:<10} {done}")
    if report["mistakes"]:
        click.echo("Often:")
        for row in report["mistakes"]:
            click.echo(f"  {row['text']} ({row['count']}x)")


# --- levels -----------------------------------------------------------------------


@main.group()
def levels() -> None:
    """List and validate levels."""


@levels.command("list")
def levels_list() -> None:
    """List bundled levels."""
    files = level_files()
    for path in files:
        try:
            level = load_level(path)
            only = f"  ({level.animal} only)" if level.signature else ""
            if level.min_python:
                skipped = skipped_reason(level)
                only += f"  [Python {version_text(level.min_python)}+" + (
                    ", locked here]" if skipped else "]"
                )
            click.echo(f"{level.id:<10} {level.shown_title}{only}")
        except LevelError as exc:
            click.echo(f"{path.relative_to(LEVELS_DIR).as_posix():<10} (invalid: {exc})")
    click.echo(f"{len(files)} level(s)")


def describe_goal(goal: dict[str, Any], world: World) -> str:
    match goal.get("type"):
        case "collect_all":
            text = f"collect every {world.pack.noun(goal['item'])}"
            if goal.get("avoid"):
                text += f", but no {world.pack.noun(goal['avoid'])}"
            return text
        case "reach":
            x, y = goal["at"]
            return f"reach square ({x}, {y})"
        case "say" if "texts" in goal:
            return "say " + ", then ".join(f'"{text}"' for text in goal["texts"])
        case "say":
            return f'say "{goal["text"]}"'
        case "avoid":
            return f"leave every {world.pack.noun(goal['item'])} alone"
        case "build":
            logs = ", ".join(f"{count} {kind}" for kind, count in goal["logs"].items())
            return f"build a dam from exactly {logs}"
        case "all":
            return " and ".join(describe_goal(part, world) for part in goal["goals"])
    return str(goal.get("type"))


@levels.command("show")
@click.argument("level")
@click.option("--animal", help="Show it for another animal (default: the level's animal).")
@click.option("--solution", is_flag=True, help="Also print the reference solution (spoiler!).")
def levels_show(level: str, animal: str | None, solution: bool) -> None:
    """Show one level: goal, limits, blocks, the grid and hints."""
    try:
        lvl = find_level(level)
        world = World.from_spec(lvl.world, load_pack(animal or lvl.animal))
    except LevelError as exc:
        raise click.ClickException(str(exc)) from None

    click.echo(_level_header(lvl, animal))
    click.echo(f"Module: {lvl.module}   Mode: {lvl.mode}   Concepts: {', '.join(lvl.concepts)}")
    click.echo(f"Goal: {describe_goal(lvl.goal, world)}")
    limits = []
    if "maxLines" in lvl.constraints:
        limits.append(f"{lvl.constraints['maxLines']} lines or fewer")
    if lvl.constraints.get("mustUse"):
        limits.append("use " + ", ".join(lvl.constraints["mustUse"]))
    click.echo(f"Stars for: {'; '.join(limits) if limits else 'just solving it'}")
    if lvl.unlocked_blocks:
        click.echo(f"Blocks: {', '.join(lvl.unlocked_blocks)}")
    click.echo(f"Start: ({world.x}, {world.y}) facing {world.facing}")
    click.echo("")
    click.echo(_indent(world.render(), "    "))
    click.echo("")
    pack = world.pack
    for number, (spec, goal) in enumerate(lvl.worlds()[1:], 2):
        other = World.from_spec(spec, pack)
        click.echo(f"World {number}: {describe_goal(goal, other)}")
        click.echo(_indent(other.render(), "    "))
        click.echo("")
    for number, hint in enumerate(lvl.shown_hints, 1):
        click.echo(f"Hint {number}: {hint}")
    if solution and lvl.path is not None:
        click.echo("")
        click.echo("Reference solution:")
        click.echo(_indent(solution_path(lvl.path).read_text(encoding="utf-8"), "    "))
    click.echo("")
    click.echo(f"Try it: codezoo check {lvl.id} your_program.py")


@levels.command("validate")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--all", "all_levels", is_flag=True, help="Validate every bundled level.")
def levels_validate(paths: tuple[Path, ...], all_levels: bool) -> None:
    """Validate level files and run each reference solution (it must earn every star)."""
    if all_levels:
        targets = level_files()
    elif paths:
        targets = [f for p in paths for f in (level_files(p) if p.is_dir() else [p])]
    else:
        raise click.UsageError("give level paths or --all")

    failed = skipped = 0
    for path in targets:
        shown = _short_path(path)
        errors = validate_level(path).errors
        reason = None
        if not errors:
            level = load_level(path)
            reason = skipped_reason(level)
            errors = [] if reason else solution_errors(level)
        if errors:
            failed += 1
            for error in errors:
                click.echo(f"FAIL  {shown}: {error}", err=True)
        elif reason:
            skipped += 1
            click.echo(f"skip  {shown}: its solution {reason}")
        else:
            click.echo(f"ok    {shown}")
    note = f" ({skipped} release-island level(s) not run on this Python)" if skipped else ""
    click.echo(f"{len(targets) - failed}/{len(targets)} level(s) valid{note}")
    if failed:
        raise SystemExit(1)


# --- graduation and the offline web build -----------------------------------------------

GRADUATION_SHIM = """\
# --- made by `codezoo graduate`: the zoo's commands, for plain Python -------------------
# In the zoo these moved an animal. Here they print what the animal would do, so the
# program runs in normal Python. Delete this part once your program doesn't need it.
def _tell(what):
    print(f"[{what}]")
def step(n=1): _tell(f"step {n}")
def turn_left(): _tell("turn left")
def turn_right(): _tell("turn right")
def grab(): _tell("grab")
def say(text=""): print(text)
# --- your program -----------------------------------------------------------------------
"""


@main.command()
@click.argument("program", type=ProgramPath)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the real-Python version here (default: PROGRAM_real.py next to it).",
)
@click.option("--run", "run_it", is_flag=True, help="Then run it in this computer's Python.")
def graduate(program: Path, output: Path | None, run_it: bool) -> None:
    """Turn PROGRAM into a plain .py file that runs in normal Python (module 15).

    The zoo's commands (step, say, ...) become small stand-ins that print what the animal
    would do. Only use --run on your own programs: real Python can do anything a program
    asks, unlike the zoo.
    """
    import subprocess

    source = program.read_text(encoding="utf-8")
    parsed = parse(source)
    if not parsed.ok:
        _echo_diagnostics(parsed)
        raise SystemExit(1)
    target = output or program.with_name(f"{program.stem}_real.py")
    target.write_text(GRADUATION_SHIM + source, encoding="utf-8")
    click.echo(f"Wrote {target}. Run it with: python {target}")
    if run_it:
        click.echo("--- running it in real Python ---")
        finished = subprocess.run([sys.executable, str(target)], check=False)
        raise SystemExit(finished.returncode)


@main.command("build-web")
@click.argument("output", type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--pyodide",
    "pyodide_url",
    default=None,
    help="Where the page loads Pyodide from (a URL or a folder next to the page). "
    "Default: the jsDelivr CDN; the page caches it after the first visit.",
)
def build_web(output: Path, pyodide_url: str | None) -> None:
    """Build the offline web version into OUTPUT: static files for any web host.

    The engine runs in the browser (Pyodide in a web worker); a service worker keeps
    everything for offline use, and players' progress stays in the browser.
    """
    from mse_codezoo.webbuild import build

    report = build(output, pyodide_url)
    click.echo(report)


# --- saved runs, storybook, cards, new worlds ------------------------------------------


def _read_run(path: Path) -> dict[str, Any]:
    from mse_codezoo.runs import RunFileError, check_run

    try:
        return check_run(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, RunFileError) as exc:
        raise click.ClickException(f"Can't read {path.name}: {exc}") from None


@main.command()
@click.argument("run_file", metavar="RUN", type=ProgramPath)
@click.option("--speed", type=click.IntRange(1, 5), default=3, show_default=True)
@click.option("--no-color", is_flag=True, help="Plain text, no colours.")
def replay(run_file: Path, speed: int, no_color: bool) -> None:
    """Replay a saved run (from `codezoo run --save`) in the terminal."""
    from mse_codezoo.term import replay as show

    data = _read_run(run_file)
    color = not no_color and sys.stdout.isatty()
    show(
        data["start"],
        data["steps"],
        str(data.get("source", "")).splitlines(),
        echo=click.echo,
        color=color,
        animate=sys.stdout.isatty(),
        speed=speed,
        header=f"Level {data.get('level')}: {data.get('title', '')}",
    )
    check_data = data.get("check") or {}
    if check_data.get("message"):
        click.echo(check_data["message"])


@main.group()
def story() -> None:
    """Storybooks made from saved runs."""


@story.command("export")
@click.argument("run_file", metavar="RUN", type=ProgramPath)
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True)
def story_export(run_file: Path, output: Path) -> None:
    """Turn a saved run into a printable HTML storybook."""
    from mse_codezoo.story import storybook_html

    output.write_text(storybook_html(_read_run(run_file)), encoding="utf-8")
    click.echo(f"Wrote {output}. Open it in a browser to add your own lines and print it.")


@main.group()
def cards() -> None:
    """Printable unplugged cards with unlock codes."""


@cards.command("print")
@click.option("--animal", default="monkey", show_default=True, help="Whose cards.")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True)
def cards_print(animal: str, output: Path) -> None:
    """Write the cards for ANIMAL as an HTML page; print it on paper or to PDF."""
    from mse_codezoo.cards import cards_html

    try:
        load_pack(animal)
    except LevelError as exc:
        raise click.ClickException(str(exc)) from None
    output.write_text(cards_html(animal, _all_levels()), encoding="utf-8")
    click.echo(f"Wrote {output}.")


@cards.command("unlock")
@click.argument("code")
@click.option("--profile", "player", required=True, help="The player who played the card.")
@_profile_errors
def cards_unlock(code: str, player: str) -> None:
    """Unlock a card's sticker with the code printed on it."""
    from mse_codezoo.cards import card_for_code

    levels = _all_levels()
    card = card_for_code(code, levels)
    if card is None:
        raise click.ClickException("That code doesn't match any card. Check the spelling.")
    result = _store().unlock_card(player, card)
    sticker = result["sticker"]
    click.echo(
        f"{sticker['emoji']} {sticker['name']}" + ("" if result["new"] else " (already yours)")
    )
    click.echo(f"Now play it on the screen: codezoo play --level {card.level_id}")


@main.group()
def world() -> None:
    """Animal worlds."""


SPEC_TEMPLATE = """# {title} world: SPEC

The plan for a new animal world, filled in before any level is built
(see "Agent workflow for a new animal world" in IMPLEMENTATION_PLAN.md).

## Characters

- The {animal}: ...

## Mechanic

- Core actions it renames (for example `grab` -> `catch`): ...
- Its own tricks, and the module each one teaches: ...

## Concept mapping

| Module | Signature level idea |
| --- | --- |
| ... | ... |

## Level list

1. {first_id}: first steps (generated by `codezoo world new`)

## Fun pass and playtest notes

- ...
"""


@world.command("new")
@click.argument("animal")
@click.option(
    "--content",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Content folder to write into (default: the bundled mse_codezoo/content).",
)
def world_new(animal: str, content: Path | None) -> None:
    """Scaffold SPEC.md, pack.json and a first level for a new animal world."""
    import re

    from mse_codezoo.levels import CONTENT_DIR

    if not re.fullmatch(r"[a-z][a-z0-9_]{1,23}", animal):
        raise click.ClickException("Animal names are lowercase letters, like 'otter'.")
    root = content or CONTENT_DIR
    folder = root / "animals" / animal
    if folder.exists():
        raise click.ClickException(f"{folder} already exists.")
    folder.mkdir(parents=True)
    actions = {
        name: name
        for name in World.from_spec({"tiles": ["."], "start": [0, 0, "east"]}).pack.all_actions()
    }
    pack = {
        "id": animal,
        "animal": animal,
        "world": "world",
        "emoji": "🐾",
        "tricks": [],
        "actions": actions,
        "items": {"B": "treat", "C": "bonus", "R": "bad"},
        "names": {
            "en": {
                "animal": animal,
                "world": "world",
                "items": {
                    "B": {"one": "treat", "many": "treats"},
                    "C": {"one": "bonus", "many": "bonuses"},
                    "R": {"one": "bad treat", "many": "bad treats"},
                },
            }
        },
    }
    (folder / "pack.json").write_text(
        json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    level_dir = root / "levels" / f"w-{animal}"
    level_dir.mkdir(parents=True, exist_ok=True)
    first_id = f"{animal}-l01"
    level = {
        "id": first_id,
        "title": "First steps",
        "module": "sequences",
        "concepts": ["sequence"],
        "animal": animal,
        "signature": True,
        "world": {"tiles": [".B"], "start": [0, 0, "east"]},
        "goal": {"type": "collect_all", "item": "B"},
        "constraints": {"maxLines": 2, "mustUse": []},
        "unlockedBlocks": ["step", "grab"],
        "hints": ["One step, then grab()."],
        "mode": "blocks_only",
    }
    (level_dir / "l01.json").write_text(json.dumps(level, indent=2) + "\n", encoding="utf-8")
    (level_dir / "l01.solution.py").write_text("step(1)\ngrab()\n", encoding="utf-8")
    title = animal.capitalize()
    (folder / "SPEC.md").write_text(
        SPEC_TEMPLATE.format(title=title, animal=animal, first_id=first_id), encoding="utf-8"
    )
    click.echo(f"Created {folder}/SPEC.md, pack.json and {level_dir}/l01.json.")
    click.echo("Fill in SPEC.md, then loop on `codezoo levels validate --all`.")
