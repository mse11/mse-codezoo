import sys

import pytest

from mse_codezoo import ir
from mse_codezoo.lang_python import block_label, outline, parse, print_program

ROUND_TRIP = [
    "step(3)\n",
    "x = (1 + 2) * -3\n",
    "x = 1 - (2 - 3)\n",
    "x = 1 - 2 - 3\n",
    "x = 2 * (3 // 4) % 5\n",
    "x = -(1 + 2)\n",
    "x = 7 / 2\n",
    "x = 2.5 + True\n",
    'say("Yum!")\n',
    "say('a \"quoted\" word')\n",
    "x = None\n",
    "x -= 1\n",
    "for i in range(5):\n    step(1)\n    grab()\n",
    "for i in range(2):\n    for j in range(3):\n        step(j)\n    turn_left()\n",
    "# note\nstep(1)  # inline\n",
    "for i in range(2):\n    # inside\n    step(1)\n    # trailing inside\n# after\n",
    "for i in range(2):\n    pass\n",
    "while True:\n    pass\n",
    "step(1)\nif x:\n    grab()\nstep(2)\n",
]


@pytest.mark.parametrize("source", ROUND_TRIP)
def test_print_then_parse_gives_the_same_program(source):
    first = parse(source)
    assert first.ok, first.diagnostics
    printed = print_program(first.program).text
    second = parse(printed)
    assert ir.to_dict(second.program, ids=False) == ir.to_dict(first.program, ids=False)


@pytest.mark.parametrize("source", ROUND_TRIP)
def test_printing_is_stable(source):
    once = print_program(parse(source).program).text
    assert print_program(parse(once).program).text == once


def test_printer_normalises_formatting():
    program = parse("x=1+2\nstep( 3 )\nsay('hi')\n").program
    assert print_program(program).text == 'x = 1 + 2\nstep(3)\nsay("hi")\n'


def test_source_map_points_at_printed_lines():
    program = parse("# a\nfor i in range(2):\n    step(1)\n    grab()\nturn_left()\n").program
    printed = print_program(program)
    lines = printed.text.splitlines()
    loop, step, grab = program.body[1], program.body[1].body[0], program.body[1].body[1]
    assert (printed.source_map[loop.id].line, printed.source_map[loop.id].end_line) == (2, 4)
    assert lines[printed.source_map[step.id].line - 1].strip() == "step(1)"
    assert printed.source_map[grab.id].col == 4


def test_positions_point_at_the_input_text():
    source = "\n\nstep(  2 )\n"
    result = parse(source)
    stmt = result.program.body[0]
    assert result.positions[stmt.id].line == 3


def test_unsupported_code_is_kept_as_raw_code_with_a_note():
    result = parse("step(1)\nwhile True:\n    # spin\n    turn_left()\nstep(2)\n")
    assert result.ok
    raw = result.program.body[1]
    assert isinstance(raw, ir.RawCode)
    assert raw.text == "while True:\n    # spin\n    turn_left()"
    assert "`while` loops" in result.diagnostics[0].message
    assert result.diagnostics[0].severity == "warning"
    # the comment inside the raw block is not duplicated outside it
    assert [type(s).__name__ for s in result.program.body] == ["ExprStmt", "RawCode", "ExprStmt"]


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("x = [1, 2]\n", "lists"),
        ("x = 2 ** 8\n", "powers"),
        ("monkey.step()\n", "this kind of call"),
        ("print('a', end='')\n", "this kind of call"),
        ("x = a < b\n", "comparisons"),
    ],
)
def test_unsupported_expressions_name_the_construct(source, reason):
    result = parse(source)
    assert isinstance(result.program.body[0], ir.RawCode)
    assert reason in result.program.body[0].reason


def test_syntax_error_gives_a_line_and_no_program():
    result = parse("step(1)\nstep(\n")
    assert not result.ok
    assert result.program is None
    assert result.errors[0].line == 2
    assert "Python can't read line 2" in result.errors[0].message


@pytest.mark.skipif(sys.version_info < (3, 12), reason="host must know 3.12 syntax")
def test_newer_syntax_is_rejected_for_the_baseline_version():
    assert not parse("type Fish = int\n", version=(3, 11)).ok
    assert parse("type Fish = int\n", version=(3, 12)).ok


def test_block_labels_and_outline():
    program = parse("# go\nfor i in range(3):\n    step(1)\nfish = 0\nfish += 1\n").program
    labels = [(depth, block_label(stmt)) for depth, stmt in outline(program)]
    assert labels == [
        (0, "note: go"),
        (0, "repeat 3 times (i counts)"),
        (1, "step 1"),
        (0, "set fish to 0"),
        (0, "change fish by +1"),
    ]
