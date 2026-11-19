import pytest

from mse_codezoo import ir
from mse_codezoo.lang_python import parse

SOURCE = """# start
x = 1  # one
for i in range(3):
    x += i * 2
step(x)
"""


def test_json_round_trip_keeps_ids_and_shape():
    program = parse(SOURCE).program
    data = ir.to_dict(program)
    assert ir.to_dict(ir.from_dict(data)) == data


def test_to_dict_without_ids_drops_every_id():
    data = ir.to_dict(parse(SOURCE).program, ids=False)
    assert "id" not in str(data.keys())
    assert "'id'" not in repr(data)


def test_inline_comment_is_kept_and_none_is_omitted():
    program = parse(SOURCE).program
    assign = program.body[1]
    assert assign.comment == "one"
    assert "comment" not in ir.to_dict(program.body[2])


def test_walk_visits_every_node_once_with_unique_ids():
    nodes = list(ir.walk(parse(SOURCE).program))
    ids = [node.id for node in nodes]
    assert len(ids) == len(set(ids))
    assert {type(n).__name__ for n in nodes} >= {"Program", "Comment", "Assign", "For", "Call"}


def test_from_dict_rejects_unknown_types():
    with pytest.raises(ValueError, match="unknown node type"):
        ir.from_dict({"type": "Teleport"})
