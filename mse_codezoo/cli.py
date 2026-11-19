"""The ``codezoo`` command line. The only module that imports click."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from mse_codezoo import __version__, ir
from mse_codezoo.game import LevelRun, run_level, solution_errors
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
from mse_codezoo.world import World

ProgramPath = click.Path(exists=True, dir_okay=False, path_type=Path)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="codezoo")
def main() -> None:
    """CodeZoo: learn real Python through animal coding games."""


# --- helpers -------------------------------------------------------------------


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
            return f"grabbed a {world.pack.item_name(item)}" if item else "nothing to grab here"
        case "say":
            return f'says "{event["text"]}"'
        case "bump":
            return "bump!"
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
    return f"Level {level.id}: {level.title} ({animal or level.animal})"


# --- run / check / blocks ----------------------------------------------------------


@main.command()
@click.argument("level")
@click.argument("program", type=ProgramPath)
@click.option("--animal", help="Play as another animal (default: the level's animal).")
@click.option("--trace", is_flag=True, help="Print every step and the grid after each move.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable output.")
def run(level: str, program: Path, animal: str | None, trace: bool, as_json: bool) -> None:
    """Run PROGRAM headless in LEVEL (a level id like m01-l01, or a level file)."""
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
        if any(e["type"] in ("move", "turn", "grab") for e in step.events):
            click.echo(_indent(world.render()))

    if not as_json:
        click.echo(_level_header(lvl, animal))
    try:
        result = run_level(lvl, source, animal=animal, on_step=on_step if trace else None)
    except LevelError as exc:
        raise click.ClickException(str(exc)) from None

    if as_json:
        click.echo(json.dumps(_run_json(result), indent=2))
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
        line = run.line_of(run.result.error.node_id)
        click.echo(f"line {line}: {run.result.error.message}", err=True)
    else:
        click.echo(f"Finished in {len(run.result.steps)} steps.")


def _run_json(run: LevelRun) -> dict[str, Any]:
    data: dict[str, Any] = {
        "level": run.level.id,
        "diagnostics": [vars(d) for d in run.parsed.diagnostics],
        "program": ir.to_dict(run.parsed.program) if run.parsed.program else None,
    }
    if run.result is not None and run.world is not None and run.check is not None:
        error = run.result.error
        data |= {
            "ok": run.result.ok,
            "error": (
                {
                    "message": error.message,
                    "node_id": error.node_id,
                    "line": run.line_of(error.node_id),
                }
                if error
                else None
            ),
            "output": run.result.output,
            "steps": [
                {**vars(step), "line": run.line_of(step.node_id)} for step in run.result.steps
            ],
            "world": run.world.to_dict(),
            "check": {
                "solved": run.check.solved,
                "message": run.check.message,
                "stars": [vars(star) for star in run.check.stars],
            },
        }
    else:
        data["ok"] = False
    return data


@main.command()
@click.argument("level")
@click.argument("program", type=ProgramPath)
@click.option("--animal", help="Play as another animal (default: the level's animal).")
def check(level: str, program: Path, animal: str | None) -> None:
    """Check PROGRAM against LEVEL's goal and constraints; print stars and hints."""
    lvl, source = _load(level, program)
    try:
        result = run_level(lvl, source, animal=animal)
    except LevelError as exc:
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
    if not outcome.solved and lvl.hints:
        click.echo(f"Hint: {lvl.hints[0]}")
    if not outcome.solved:
        raise SystemExit(1)


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
            click.echo(f"{level.id:<10} {level.title}")
        except LevelError as exc:
            click.echo(f"{path.relative_to(LEVELS_DIR).as_posix():<10} (invalid: {exc})")
    click.echo(f"{len(files)} level(s)")


def describe_goal(goal: dict[str, Any], world: World) -> str:
    match goal.get("type"):
        case "collect_all":
            return f"collect every {world.pack.item_name(goal['item'])}"
        case "reach":
            x, y = goal["at"]
            return f"reach square ({x}, {y})"
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
    for number, hint in enumerate(lvl.hints, 1):
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

    failed = 0
    for path in targets:
        shown = _short_path(path)
        errors = validate_level(path).errors
        if not errors:
            errors = solution_errors(load_level(path))
        if errors:
            failed += 1
            for error in errors:
                click.echo(f"FAIL  {shown}: {error}", err=True)
        else:
            click.echo(f"ok    {shown}")
    click.echo(f"{len(targets) - failed}/{len(targets)} level(s) valid")
    if failed:
        raise SystemExit(1)
