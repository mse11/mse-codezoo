"""The playground examples behave as playground/README.md says."""

from pathlib import Path

import pytest

from mse_codezoo.cli import own_modules
from mse_codezoo.game import run_level
from mse_codezoo.levels import find_level

PLAYGROUND = Path(__file__).parents[1] / "playground"

STARS = {
    "m01-l01.py": 3,
    "m01-l02.py": 3,
    "m01-l03.py": 3,
    "m01-l04.py": 3,
    "m01-l05.py": 3,
    "m02-l01.py": 3,
    "m02-l01-no-loop.py": 1,
    "m03-l02.py": 3,
    "m04-l04.py": 3,
    "m05-l03.py": 3,
    "m07-l03.py": 2,
    "m07-l05.py": 3,
    "m08-l02.py": 3,
    "m09-l06.py": 3,
    "m10-l06.py": 3,
}
HELPERS = {"mytricks.py"}  # imported by an example, not a level's program

OOPS = {
    "bump.py": ("m01-l03", "Bump! The monkey walked into a wall."),
    "typo.py": ("m01-l01", "Did you mean `step`?"),
    "syntax.py": ("m01-l01", "Python can't read line"),
    "too-short.py": ("m01-l01", "1 banana still to collect."),
    "for-else.py": ("m01-l01", "CodeZoo can't run `For` yet."),
    "no-brackets.py": ("m05-l01", "Add brackets to ask it: `is_blocked()`."),
    "one-world.py": ("m05-l02", "It works here, but not in world 2"),
    "no-base-case.py": ("m10-l01", "Does it have a base case"),
    "thin-ice.py": ("m08-l02", "Crack! The ice ahead is too thin"),
    "no-global.py": ("m07-l11", "write `global score` first"),
}


def play(level_id, path):
    source = path.read_text(encoding="utf-8")
    return run_level(find_level(level_id), source, modules=own_modules(path, source))


def test_every_example_is_listed():
    assert {p.name for p in PLAYGROUND.glob("*.py")} == set(STARS) | HELPERS
    assert {p.name for p in (PLAYGROUND / "oops").glob("*.py")} == set(OOPS)


@pytest.mark.parametrize("name", STARS)
def test_examples_solve_their_level(name):
    run = play(name[:7], PLAYGROUND / name)
    assert run.check is not None and run.check.solved
    assert run.check.earned == STARS[name]


@pytest.mark.parametrize("name", OOPS)
def test_oops_examples_fail_with_a_friendly_message(name):
    level_id, message = OOPS[name]
    run = play(level_id, PLAYGROUND / "oops" / name)
    if run.check is None:  # could not even be parsed
        text = " ".join(d.message for d in run.parsed.errors)
    else:
        assert not run.check.solved
        text = run.check.message
    assert message in text
