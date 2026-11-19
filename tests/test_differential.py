"""Our interpreter and CPython must agree on every program in the supported subset."""

import subprocess
import sys

import pytest

from mse_codezoo.interpreter import run
from mse_codezoo.lang_python import parse

PROGRAMS = {
    "arithmetic": "x = 7\ny = 2\nprint(x + y, x - y, x * y, x / y, x // y, x % y)\n",
    "negative": "print(-7 // 2, -7 % 2, 7 // -2, -(3 - 5), +4)\n",
    "floats": "print(0.1 + 0.2, 1 / 3, 2.5 * 4, round(2.675, 2), round(3.5))\n",
    "precedence": "print(2 + 3 * 4, (2 + 3) * 4, 10 - 4 - 3, 10 - (4 - 3), 2 * -3)\n",
    "variables": "fish = 0\nfish = fish + 1\nfish += 2\nfish *= 3\nfish -= 1\nprint(fish)\n",
    "loop": "total = 0\nfor i in range(1, 11):\n    total += i\nprint(total)\n",
    "nested": "for i in range(3):\n    for j in range(i):\n        print(i, j)\n",
    "range_step": "for i in range(10, 0, -3):\n    print(i)\n",
    "strings": "name = 'Momo'\nprint('Hi ' + name + '!', 'ab' * 3, str(5) + str(2.5))\n",
    "string_loop": "for letter in 'zoo':\n    print(letter)\n",
    "builtins": "print(len('banana'), abs(-4), min(3, 1, 2), max(2, 9), int('42'), float('1.5'))\n",
    "bools": "print(True + 1, bool(0), bool('x'), int(True), str(None))\n",
    "loop_var_after": "for i in range(3):\n    pass\nprint(i)\n",
    "comments": "# a note\nx = 1  # inline\nprint(x)\n",
    "empty_print": "print()\nprint('')\n",
}

ERRORS = {
    "zero_division": "print(1 / 0)\n",
    "type_mix": "print('a' + 1)\n",
    "undefined": "print(banana)\n",
    "bad_int": "print(int('x'))\n",
}


def cpython(source):
    return subprocess.run(
        [sys.executable, "-I", "-c", source],
        capture_output=True,
        text=True,
        timeout=30,
    )


def ours(source):
    parsed = parse(source)
    assert parsed.ok, parsed.diagnostics
    return run(parsed.program)


@pytest.mark.parametrize("name", PROGRAMS)
def test_same_output_as_cpython(name):
    source = PROGRAMS[name]
    expected = cpython(source)
    assert expected.returncode == 0, expected.stderr
    result = ours(source)
    assert result.ok, result.error
    assert result.output == expected.stdout.splitlines()


@pytest.mark.parametrize("name", ERRORS)
def test_fails_where_cpython_fails(name):
    source = ERRORS[name]
    assert cpython(source).returncode != 0
    assert not ours(source).ok
