"""The IR JSON Schema: generated from ir.py, bundled as ir.schema.json, and accurate."""

import copy
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from jsonschema import Draft202012Validator

from mse_codezoo import ir
from mse_codezoo.cli import main
from mse_codezoo.lang_python import parse
from mse_codezoo.levels import level_files, solution_path

BUNDLED = Path(ir.__file__).with_name("ir.schema.json")
VALIDATOR = Draft202012Validator(ir.json_schema())

SOURCES = [
    "step(3)\n",
    "# note\nx = (1 + 2) * -3  # inline\nx += 1\n",
    "for i in range(5):\n    step(1)\n    grab()\n",
    "for i in range(2):\n    pass\n",
    "say('hi')\nx = None\ny = True\nz = 2.5\n",
    "class Spin:\n    pass\n",  # RawCode
    "def spin(n, k=2):\n    global x\n    return n, k\n",
    (
        "try:\n    a = [1, *b]\nexcept (KeyError, ValueError) as e:\n    raise\n"
        "else:\n    del a[0]\nfinally:\n    pass\n"
    ),
    (
        "import tricks\nfrom tricks import x\nd = {'a': 1, **e}\n"
        "x, *y = {k: v for k, v in d.items() if v}\nprint(tricks.x, {1, 2}, (1,))\n"
    ),
    "for a, b in z:\n    if a:\n        break\n    continue\nassert a, 'no'\n",
    (
        "if is_blocked():\n    turn_left()\nelif item_here() == 'banana' and not x:\n"
        "    grab()\nelse:\n    step()\n"
    ),
    "while n < 3 or -n ** 2 >= 1:\n    n += 1\n",
    "say(f'{n!r:>3} bananas')\nprint(name.upper()[1:3], name[0], end='')\ny = 'a' if n else 'b'\n",
    "",
]


def program_dict(source):
    result = parse(source)
    assert result.ok, result.diagnostics
    return ir.to_dict(result.program)


def errors(data):
    return list(VALIDATOR.iter_errors(data))


def test_bundled_schema_matches_the_dataclasses():
    expected = json.dumps(ir.json_schema(), indent=2) + "\n"
    assert BUNDLED.read_text(encoding="utf-8") == expected, (
        "ir.schema.json is out of date; run `uv run codezoo schema -o mse_codezoo/ir.schema.json`"
    )


def test_schema_is_a_valid_draft_2020_12_schema():
    Draft202012Validator.check_schema(ir.json_schema())


def test_every_node_type_has_a_definition():
    defs = ir.json_schema()["$defs"]
    assert set(ir.NODE_TYPES) <= set(defs)
    expr_members = {ref["$ref"].rsplit("/", 1)[1] for ref in defs["Expr"]["oneOf"]}
    stmt_members = {ref["$ref"].rsplit("/", 1)[1] for ref in defs["Stmt"]["oneOf"]}
    assert expr_members == {
        "Const",
        "Name",
        "Call",
        "MethodCall",
        "BinOp",
        "UnaryOp",
        "Compare",
        "BoolOp",
        "IfExp",
        "FormattedValue",
        "FString",
        "Slice",
        "Subscript",
        "Attribute",
        "List",
        "Tuple",
        "Set",
        "Dict",
        "Starred",
        "Comprehension",
    }
    assert stmt_members == {
        "ExprStmt",
        "Assign",
        "AugAssign",
        "For",
        "If",
        "While",
        "Break",
        "Continue",
        "FunctionDef",
        "Return",
        "Global",
        "Try",
        "Raise",
        "Assert",
        "Delete",
        "Import",
        "Pass",
        "Comment",
        "RawCode",
    }


@pytest.mark.parametrize("source", SOURCES)
def test_parsed_programs_are_valid(source):
    assert errors(program_dict(source)) == []


@pytest.mark.parametrize("path", level_files(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_reference_solution_is_valid(path):
    source = solution_path(path).read_text(encoding="utf-8")
    assert errors(program_dict(source)) == []


def test_run_json_program_is_valid(tmp_path):
    program = tmp_path / "p.py"
    program.write_text("step(4)\ngrab()\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["run", "m01-l01", str(program), "--json"])
    assert errors(json.loads(result.output)["program"]) == []


BASE = "for i in range(2):\n    step(1)\n"


def broken(change):
    data = program_dict(BASE)
    change(data)
    return data


def set_in(path, value):
    def change(data):
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return change


@pytest.mark.parametrize(
    "change",
    [
        set_in(["body", 0, "type"], "Teleport"),  # unknown node type
        set_in(["body", 0, "body", 0, "value", "args"], "1"),  # args must be a list
        set_in(["body", 0, "body", 0, "value", "func"], 7),  # func must be text
        set_in(["body", 0, "id"], ""),  # empty id
        set_in(["body", 0, "body", 0, "extra"], 1),  # unknown field
        set_in(["body", 0, "iter"], {"type": "Pass", "id": "x"}),  # statement as expression
        set_in(["body", 0, "body", 0], {"type": "Name", "id": "x", "name": "a"}),  # expr as stmt
        set_in(["body", 0, "target"], {"type": "Pass", "id": "x"}),  # target: an expression
        set_in(["body", 0, "body", 0, "value", "args", 0, "value"], [1]),  # Const of a list
        lambda data: data["body"][0].pop("iter"),  # missing required field
        lambda data: data.pop("id"),  # program without id
    ],
)
def test_invalid_programs_are_rejected(change):
    assert errors(broken(change)), "expected the schema to reject this program"


def test_base_program_itself_is_valid():
    assert errors(copy.deepcopy(program_dict(BASE))) == []


def test_schema_command_prints_the_schema():
    result = CliRunner().invoke(main, ["schema"])
    assert result.exit_code == 0
    assert json.loads(result.output) == ir.json_schema()


def test_schema_command_writes_a_file(tmp_path):
    target = tmp_path / "ir.schema.json"
    result = CliRunner().invoke(main, ["schema", "-o", str(target)])
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text(encoding="utf-8"))["$id"] == "urn:mse-codezoo:ir:v3"
