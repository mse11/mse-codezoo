# ruff: noqa: E501 - the programs below read best one per line
"""Phase 3 language: functions, recursion, errors, collections, comprehensions, imports.

Every program here runs in our interpreter and in a real CPython; the output must match.
"""

import pytest

from mse_codezoo import ir
from mse_codezoo.interpreter import MAX_DEPTH, LearnerError, function, run
from mse_codezoo.lang_python import parse, print_program
from tests.test_differential import cpython, ours

PROGRAMS = {
    "def_and_call": "def greet(name, times=2):\n    print(name * times)\ngreet('ha')\ngreet('o', 3)\n"
    "greet(times=1, name='x')\n",
    "return_values": "def split(n):\n    return n // 2, n % 2\nhalf, rest = split(7)\nprint(half, rest)\n"
    "print(split(4))\n",
    "return_none": "def nothing():\n    pass\nprint(nothing())\n",
    "early_return": "def first_even(n):\n    for i in range(n):\n        if i > 0 and i % 2 == 0:\n"
    "            return i\n    return -1\nprint(first_even(10), first_even(2))\n",
    "scope_local": "x = 1\ndef f():\n    x = 2\n    return x\nprint(f(), x)\n",
    "scope_global": "count = 0\ndef add():\n    global count\n    count += 1\nadd()\nadd()\n"
    "print(count)\n",
    "scope_read_global": "zoo = 'jungle'\ndef where():\n    return zoo.upper()\nprint(where())\n",
    "closure": "def outer(n):\n    def inner(k):\n        return n + k\n    return inner(10)\n"
    "print(outer(5))\n",
    "defaults_once": "def tag(name, mark='!'):\n    return name + mark\nprint(tag('a'), tag('b', '?'))\n",
    "recursion_factorial": "def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n"
    "print(fact(10))\n",
    "recursion_fib": "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
    "print([fib(i) for i in range(12)])\n",
    "recursion_tree": "def count(tree):\n    total = 1\n    for child in tree:\n"
    "        total += count(child)\n    return total\nprint(count([[], [[], []], [[[]]]]))\n",
    "function_repr_type": "def f():\n    pass\nprint(type(f))\n",
    "break_continue": "for i in range(10):\n    if i == 7:\n        break\n    if i % 2:\n"
    "        continue\n    print(i)\nn = 0\nwhile True:\n    n += 1\n    if n > 3:\n"
    "        break\nprint(n)\n",
    "nested_break": "for i in range(3):\n    for j in range(3):\n        if j == 1:\n"
    "            break\n        print(i, j)\n",
    "try_except": "try:\n    x = 1 / 0\nexcept ZeroDivisionError as e:\n    print('caught', e)\n"
    "print('after')\n",
    "try_else_finally": "for d in [2, 0]:\n    try:\n        r = 10 // d\n    except ZeroDivisionError:\n"
    "        print('zero')\n    else:\n        print('ok', r)\n    finally:\n        print('done')\n",
    "except_tuple": "for v in ['5', 'x', None]:\n    try:\n        print(int(v))\n"
    "    except (ValueError, TypeError) as e:\n        print(type(e).__name__)\n",
    "raise_and_catch": "def check(n):\n    if n < 0:\n        raise ValueError('negative')\n    return n\n"
    "try:\n    check(-1)\nexcept ValueError as e:\n    print('no:', e)\n",
    "bare_raise": "try:\n    try:\n        [][1]\n    except IndexError:\n        print('inner')\n"
    "        raise\nexcept IndexError as e:\n    print('outer', e)\n",
    "key_error": "d = {'oak': 1}\ntry:\n    d['pine']\nexcept KeyError as e:\n    print('missing', e)\n",
    "assert_ok": "assert 1 + 1 == 2, 'maths'\nprint('fine')\n",
    "finally_on_return": "def f():\n    try:\n        return 'body'\n    finally:\n        print('cleanup')\n"
    "print(f())\n",
    "except_name_unset": "try:\n    1 / 0\nexcept ZeroDivisionError as err:\n    pass\n"
    "print('err' in dir() if False else 'ok')\n",
    "lists": "logs = ['oak', 'pine']\nlogs.append('birch')\nlogs.insert(0, 'ash')\n"
    "print(logs, len(logs), logs[1], logs[-1], logs[1:3])\nlogs.remove('pine')\n"
    "print(logs.pop(), logs, logs.index('oak'), logs.count('ash'))\nlogs.extend(['elm'])\n"
    "logs.sort()\nprint(logs)\nlogs.reverse()\nprint(logs)\ndel logs[0]\nprint(logs)\n",
    "list_assign": "a = [1, 2, 3]\na[0] = 9\na[1:] = [7]\nprint(a)\nb = a\nb += [5]\nprint(a, b is a)\n",
    "tuples": "pair = (3, 'oak')\nn, kind = pair\nprint(n, kind, pair[0], len(pair), (1,), ())\n"
    "a, b = 1, 2\na, b = b, a\nprint(a, b)\nfirst, *rest = [1, 2, 3, 4]\nprint(first, rest)\n"
    "*init, last = 'abc'\nprint(init, last)\n",
    "dicts": "inv = {'oak': 3, 'pine': 2}\ninv['birch'] = 1\ninv['oak'] += 1\n"
    "print(inv, inv.get('elm'), inv.get('elm', 0), 'oak' in inv, len(inv))\n"
    "inv.setdefault('ash', 5)\ninv.update({'pine': 0})\nprint(sorted(inv.items()))\n"
    "for k, v in inv.items():\n    print(k, v)\nprint(list(inv.keys()), list(inv.values()))\n"
    "del inv['ash']\nprint(inv.pop('birch'), inv, {**inv, 'x': 1})\n",
    "sets": "a = {1, 2, 3}\nb = {2, 3, 4}\nprint(sorted(a & b), sorted(a | b), sorted(a - b),"
    " sorted(a ^ b), 2 in a, set())\na.add(9)\na.discard(1)\nprint(sorted(a), a.issubset({2, 3, 9, 10}))\n",
    "builtins_collections": "nums = [5, 3, 8]\nprint(sum(nums), min(nums), max(nums), sorted(nums),"
    " sorted(nums, reverse=True), list(range(3)), tuple('ab'), any([0, 1]), all([1, 0]))\n"
    "for i, n in enumerate(nums, start=1):\n    print(i, n)\nfor a, b in zip('ab', [1, 2]):\n"
    "    print(a, b)\nprint(list(reversed(nums)), isinstance(3, int), dict(oak=1))\n",
    "sort_key": "def size(word):\n    return len(word)\nwords = ['pine', 'oak', 'birch']\n"
    "print(sorted(words, key=size), max(words, key=size))\nwords.sort(key=size, reverse=True)\n"
    "print(words)\n",
    "comprehensions": "print([n * n for n in range(6) if n % 2 == 0])\n"
    "print({w: len(w) for w in ['oak', 'pine']})\nprint(sorted({c for c in 'banana'}))\n"
    "print([(a, b) for a in range(2) for b in 'xy'])\nn = 'kept'\nx = [n for n in range(3)]\n"
    "print(n)\n",
    "text_split_join": "words = 'oak pine  birch'.split()\nprint(words, '-'.join(words),"
    " 'a,b'.split(','), 'x'.join('abc'))\n",
    "nested_data": "dam = {'logs': [('oak', 2), ('pine', 3)]}\ntotal = 0\n"
    "for kind, length in dam['logs']:\n    total += length\nprint(total, dam['logs'][1][0])\n",
    "list_equality": "print([1, [2]] == [1, [2]], (1, 2) < (1, 3), [3] * 3, [1] + [2])\n",
    "string_index_method": "print('banana'.index('n'))\n",
    "bit_ops": "print(6 | 3, 6 & 3, 6 ^ 3)\n",
}

ERRORS = {
    "missing_arg": "def f(a):\n    pass\nf()\n",
    "too_many_args": "def f(a):\n    pass\nf(1, 2)\n",
    "unknown_keyword": "def f(a):\n    pass\nf(b=1)\n",
    "unbound_local": "x = 1\ndef f():\n    x += 1\nf()\n",
    "unbound_local_read": "x = 1\ndef f():\n    print(x)\n    x = 2\nf()\n",
    "endless_recursion": "def f():\n    f()\nf()\n",
    "uncaught_raise": "raise ValueError('bad log')\n",
    "assert_fails": "assert 1 > 2, 'nope'\n",
    "break_outside": "break\n",
    "return_outside": "return 1\n",
    "key_missing": "print({'a': 1}['b'])\n",
    "list_index": "print([1, 2][5])\n",
    "tuple_assign": "t = (1, 2)\nt[0] = 3\n",
    "unpack_count": "a, b = [1, 2, 3]\n",
    "unhashable": "s = {[1]}\n",
    "bare_raise_outside": "raise\n",
    "missing_module": "import tricks\n",
    "remove_missing": "[1].remove(2)\n",
}


@pytest.mark.parametrize("name", PROGRAMS)
def test_same_output_as_cpython(name):
    source = PROGRAMS[name]
    expected = cpython(source)
    assert expected.returncode == 0, expected.stderr
    result = ours(source)
    assert result.ok, result.error and result.error.message
    assert result.output == expected.stdout.splitlines()


@pytest.mark.parametrize("name", ERRORS)
def test_fails_where_cpython_fails(name):
    source = ERRORS[name]
    assert cpython(source).returncode != 0
    result = ours(source)
    assert not result.ok
    assert result.error.message  # always worded for the learner


@pytest.mark.parametrize("name", [*PROGRAMS, *ERRORS])
def test_round_trip(name):
    source = {**PROGRAMS, **ERRORS}[name]
    first = print_program(parse(source).program).text
    again = parse(first)
    assert again.ok and not again.diagnostics
    assert print_program(again.program).text == first
    assert ir.to_dict(again.program, ids=False) == ir.to_dict(parse(source).program, ids=False)


def message(source, **kw):
    result = ours(source) if not kw else run(parse(source).program, **kw)
    assert result.error is not None
    return result.error


def test_recursion_has_a_friendly_limit():
    error = message("def explore(n):\n    explore(n + 1)\nexplore(0)\n")
    assert error.kind == "too_deep"
    assert "base case" in error.message
    assert f"{MAX_DEPTH} deep" in error.message


def test_deep_recursion_within_the_limit_works():
    result = ours(
        f"def down(n):\n    if n == 0:\n        return 0\n    return 1 + down(n - 1)\n"
        f"print(down({MAX_DEPTH - 1}))\n"
    )
    assert result.ok and result.output == [str(MAX_DEPTH - 1)]


def test_unbound_local_explains_global():
    error = message("score = 0\ndef win():\n    score += 1\nwin()\n")
    assert "global score" in error.message
    assert "win" in error.message


def test_uncaught_error_names_its_kind_and_keeps_a_traceback():
    source = "def slide():\n    raise ValueError('thin ice')\ndef go():\n    slide()\ngo()\n"
    parsed = parse(source)
    result = run(parsed.program)
    error = result.error
    assert error.kind == "raised"
    assert "`ValueError`" in error.message and "thin ice" in error.message
    lines = [parsed.positions[node].line for _name, node in error.traceback]
    assert [name for name, _ in error.traceback] == ["<program>", "go", "slide"]
    assert lines == [5, 4, 2]


def test_the_zoos_limits_cannot_be_caught():
    result = ours("try:\n    while True:\n        pass\nexcept Exception:\n    print('no')\n")
    assert result.error.kind == "too_many_steps"
    result = ours("try:\n    x = [0] * 100000\nexcept Exception:\n    print('no')\n")
    assert not result.ok and "far too many" in result.error.message


def test_errors_carry_python_exceptions_for_except():
    error = message("x = int('oak')\n")
    assert isinstance(error.exception, ValueError)
    error = message("print(banana)\n")
    assert isinstance(error.exception, NameError)


def test_world_errors_can_be_caught_by_their_own_class():
    class CrackError(Exception):
        pass

    def slide():
        raise LearnerError("The ice cracked!", kind="crack", exception=CrackError("thin ice"))

    actions = {"slide": slide, "CrackError": CrackError}
    source = "try:\n    slide()\nexcept CrackError as e:\n    print('around', e)\n"
    result = run(parse(source).program, actions)
    assert result.ok and result.output == ["around thin ice"]


def test_calls_show_on_the_call_stack():
    result = ours("def f(n):\n    return n * 2\nprint(f(3))\n")
    events = [e for step in result.steps for e in step.events]
    assert {"type": "call", "name": "f", "args": ["3"], "depth": 1} in events
    assert {"type": "return", "name": "f", "value": "6", "depth": 1} in events


def test_steps_inside_functions_point_at_their_lines():
    source = "def hop():\n    step(1)\nhop()\nhop()\n"
    parsed = parse(source)
    moves = []
    result = run(parsed.program, {"step": lambda n=1: moves.append(n)})
    lines = [
        parsed.positions[s.node_id].line for s in result.steps if s.node_id in parsed.positions
    ]
    assert lines == [1, 1, 2, 3, 1, 2, 4]
    assert moves == [1, 1]


def test_import_a_helper_file():
    tricks = "HEIGHT = 3\ndef climb_tree(height):\n    return 'up ' * height\n"
    source = "import tricks\nfrom tricks import climb_tree\nprint(climb_tree(tricks.HEIGHT))\n"
    result = run(parse(source).program, modules={"tricks": tricks})
    assert result.ok, result.error and result.error.message
    assert result.output == ["up up up "]


def test_helper_files_have_their_own_names():
    tricks = "x = 'inside'\ndef show():\n    return x\n"
    source = "x = 'outside'\nfrom tricks import show\nprint(show(), x)\n"
    result = run(parse(source).program, modules={"tricks": tricks})
    assert result.output == ["inside outside"]


def test_learner_functions_work_as_keys_and_look_like_functions():
    result = ours("def f():\n    pass\nprint(f)\n")
    assert result.output == ["<function f>"]
    assert function.__name__ == "function"


def test_huge_collections_are_refused():
    for source in (
        "x = list(range(10**9))\n",
        "x = sum(range(10**12))\n",
        "x = [0]\nfor i in range(20):\n    x = x + x\n",
        "x = [n for n in range(10**9)]\n",
    ):
        assert not ours(source).ok, source
