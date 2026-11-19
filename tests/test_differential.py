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
    "if_elif_else": (
        "for n in range(-2, 5):\n    if n < 0:\n        print(n, 'neg')\n"
        "    elif n == 0:\n        print('zero')\n    elif n % 2 == 0:\n        print(n, 'even')\n"
        "    else:\n        print(n, 'odd')\n"
    ),
    "while": "n = 1\nwhile n < 100:\n    n = n * 3\nprint(n)\n",
    "while_false": "while False:\n    print('never')\nprint('done')\n",
    "compare_chain": (
        "x = 2\nprint(1 < x < 3, 1 < x > 5, x == 2.0, 'a' < 'b', x != 2, 3 >= x >= 2)\n"
    ),
    "bool_ops": "print(0 or 'x', '' and 1, 3 and 4, not 0, not 'a', None or 0, 1 or 1 / 0)\n",
    "truthiness": "for v in range(3):\n    print(v if v else 'zero', 'yes' if '' else 'no')\n",
    "is_none": "x = None\nprint(x is None, x is not None, 5 is not None, x == None)\n",
    "in_text": "print('an' in 'banana', 'x' not in 'banana', 3 in range(5))\n",
    "powers": "print(2 ** 10, 2 ** -1, -2 ** 2, (-2) ** 2, 2 ** 3 ** 2, 2.5 ** 2, 0 ** 0)\n",
    "fstrings": (
        "name = 'Momo'\nn = 3\nprint(f'{name} has {n} bananas', f'{n * 2.5:.1f}', f'{name!r}',"
        " f'{n:>4}|', f'{name:<6}|', f'{{x}}', f'{n:03d}', f'{0.5:.0%}')\n"
    ),
    "string_methods": (
        "s = '  Hello Jungle  '\nprint(s.strip(), s.upper(), s.lower(), s.strip().title(),"
        " s.count('l'), s.find('J'), s.replace('l', 'L'), s.strip().startswith('He'),"
        " 'abc'.endswith('c'), '42'.isdigit(), 'ab'.isalpha(), 'x'.center(5, '*'),"
        " '7'.zfill(3), 'ab'.capitalize(), 'aB'.swapcase(), (2.0).is_integer())\n"
    ),
    "format_method": (
        "print('{} and {}'.format('a', 2), '{1}{0}'.format('x', 'y'), '{:>3}'.format(7))\n"
    ),
    "indexing": (
        "s = 'banana'\nprint(s[0], s[-1], s[1:4], s[:2], s[3:], s[::2], s[::-1], s[10:], len(s))\n"
        "for i in range(len(s)):\n    print(s[i], end='')\nprint()\n"
    ),
    "type_and_conversion": (
        "print(type(5), type(2.5), type('a'), type(True), type(None), type(5) == int,"
        " int('7') + 1, float(3), str(4) + '!', int(3.9), round(2.5), bool(''))\n"
    ),
    "print_keywords": (
        "print(1, 2, 3, sep=', ')\nprint('a', end='')\nprint('b')\nprint('x', 'y', sep='')\n"
        "print('no newline at the end', end='')\n"
    ),
}

ERRORS = {
    "zero_division": "print(1 / 0)\n",
    "type_mix": "print('a' + 1)\n",
    "undefined": "print(banana)\n",
    "bad_int": "print(int('x'))\n",
    "compare_types": "print('a' < 1)\n",
    "index_out_of_range": "print('abc'[5])\n",
    "index_with_text": "print('abc'['a'])\n",
    "unknown_method": "print('abc'.shout())\n",
    "zero_in_power": "print(0 ** -1)\n",
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
