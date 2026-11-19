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

## Layout

```
mse_codezoo/        the package (flat layout, no src/)
  cli.py            click commands
  levels.py         level discovery and validation
  content/levels/   level JSON + reference solutions (<id>.solution.py)
  content/animals/  animal packs
tests/
```

## Commands so far

| Command | Status |
| --- | --- |
| `codezoo levels list` | Works |
| `codezoo levels validate [--all] [PATHS...]` | Checks JSON shape and that a reference solution exists |
| `codezoo run`, `check`, `blocks` | Stubs until the interpreter lands |
