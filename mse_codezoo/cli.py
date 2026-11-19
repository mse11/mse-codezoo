"""The ``codezoo`` command line. The only module that imports click."""

from __future__ import annotations

from pathlib import Path

import click

from mse_codezoo import __version__
from mse_codezoo.levels import LEVELS_DIR, level_files, validate_level

NOT_YET = "not implemented yet (phase 0)"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="codezoo")
def main() -> None:
    """CodeZoo: learn real Python through animal coding games."""


@main.command()
@click.argument("level")
@click.argument("program", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--trace", is_flag=True, help="Print every step.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable output.")
def run(level: str, program: Path, trace: bool, as_json: bool) -> None:
    """Run PROGRAM headless in LEVEL."""
    raise click.ClickException(NOT_YET)


@main.command()
@click.argument("level")
@click.argument("program", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def check(level: str, program: Path) -> None:
    """Check PROGRAM against LEVEL's goal and constraints; print stars and hints."""
    raise click.ClickException(NOT_YET)


@main.command()
@click.argument("program", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def blocks(program: Path) -> None:
    """Print PROGRAM as a block outline with its source map."""
    raise click.ClickException(NOT_YET)


@main.group()
def levels() -> None:
    """List and validate levels."""


@levels.command("list")
def levels_list() -> None:
    """List bundled level files."""
    files = level_files()
    for path in files:
        click.echo(path.relative_to(LEVELS_DIR).as_posix())
    click.echo(f"{len(files)} level(s)")


@levels.command("validate")
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--all", "all_levels", is_flag=True, help="Validate every bundled level.")
def levels_validate(paths: tuple[Path, ...], all_levels: bool) -> None:
    """Validate level files (JSON shape and reference solution)."""
    if all_levels:
        targets = level_files()
    elif paths:
        targets = [f for p in paths for f in (level_files(p) if p.is_dir() else [p])]
    else:
        raise click.UsageError("give level paths or --all")

    failed = 0
    for path in targets:
        report = validate_level(path)
        if report.ok:
            click.echo(f"ok    {path.name}")
        else:
            failed += 1
            for error in report.errors:
                click.echo(f"FAIL  {path.name}: {error}", err=True)
    click.echo(f"{len(targets) - failed}/{len(targets)} level(s) valid")
    if failed:
        raise SystemExit(1)
