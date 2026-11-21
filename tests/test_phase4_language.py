"""Phase 4 language: generators, lambda, classes, decorators, `with`, `match`, async and
threads. Each program must print exactly what CPython prints, and round-trip as text."""

import subprocess
import sys

import pytest

from mse_codezoo import ir
from mse_codezoo.interpreter import LearnerError, run
from mse_codezoo.lang_python import parse, print_program

PROGRAMS = {
    "lambda_sort": (
        "logs = [('oak', 3), ('pine', 1), ('birch', 2)]\n"
        "print(sorted(logs, key=lambda log: log[1]))\n"
        "double = lambda x, times=2: x * times\n"
        "print(double(4), double(4, times=3))\n"
    ),
    "map_filter": (
        "print(list(map(lambda n: n * n, range(5))))\n"
        "print(list(filter(lambda n: n % 2, range(10))))\n"
        "print(list(zip('ab', [1, 2])), list(enumerate('xy', start=1)))\n"
    ),
    "generator": (
        "def honey(n):\n"
        "    for drop in range(n):\n"
        "        print('make', drop)\n"
        "        yield drop * 10\n"
        "    return 'jar full'\n"
        "jar = honey(3)\n"
        "print(next(jar))\n"
        "print(next(jar))\n"
        "for rest in jar:\n"
        "    print('got', rest)\n"
        "try:\n"
        "    next(jar)\n"
        "except StopIteration:\n"
        "    print('empty')\n"
    ),
    "generator_return_value": (
        "def inner():\n"
        "    yield 1\n"
        "    return 'done'\n"
        "def outer():\n"
        "    result = yield from inner()\n"
        "    yield result\n"
        "print(list(outer()))\n"
    ),
    "infinite_pipeline": (
        "def flowers():\n"
        "    n = 0\n"
        "    while True:\n"
        "        n += 1\n"
        "        yield n\n"
        "def nectar(source):\n"
        "    for f in source:\n"
        "        if f % 2 == 0:\n"
        "            yield f * 3\n"
        "pipe = nectar(flowers())\n"
        "print([next(pipe) for _ in range(4)])\n"
    ),
    "send": (
        "def counter():\n"
        "    total = 0\n"
        "    while True:\n"
        "        got = yield total\n"
        "        total += got\n"
        "c = counter()\n"
        "next(c)\n"
        "print(c.send(5), c.send(2))\n"
    ),
    "genexp": (
        "print(sum(x * x for x in range(10)))\n"
        "g = (c.upper() for c in 'bee' if c != 'x')\n"
        "print(next(g), list(g))\n"
        "print(max((len(w), w) for w in ['ant', 'bee', 'wasp']))\n"
    ),
    "classes": (
        "class Bee:\n"
        "    count = 0\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "        Bee.count += 1\n"
        "    def work(self):\n"
        "        return f'{self.name} rests'\n"
        "    def __str__(self):\n"
        "        return f'Bee {self.name}'\n"
        "class Worker(Bee):\n"
        "    def __init__(self, name, flowers):\n"
        "        super().__init__(name)\n"
        "        self.flowers = flowers\n"
        "    def work(self):\n"
        "        return f'{self.name} visits {self.flowers} flowers'\n"
        "class Drone(Bee):\n"
        "    pass\n"
        "hive = [Worker('Bea', 3), Drone('Dan'), Worker('Ola', 5)]\n"
        "for bee in hive:\n"
        "    print(bee.work())\n"
        "print(Bee.count, str(hive[1]), isinstance(hive[0], Bee), issubclass(Drone, Worker))\n"
        "print(type(hive[0]).__name__, [c.__name__ for c in Worker.__mro__])\n"
    ),
    "property_and_methods": (
        "class Jar:\n"
        "    size = 3\n"
        "    def __init__(self):\n"
        "        self._drops = 0\n"
        "    @property\n"
        "    def drops(self):\n"
        "        return self._drops\n"
        "    @drops.setter\n"
        "    def drops(self, value):\n"
        "        self._drops = min(value, self.size)\n"
        "    @classmethod\n"
        "    def big(cls):\n"
        "        jar = cls()\n"
        "        jar.size = 10\n"
        "        return jar\n"
        "    @staticmethod\n"
        "    def label(n):\n"
        "        return f'{n} drops'\n"
        "j = Jar()\n"
        "j.drops = 7\n"
        "b = Jar.big()\n"
        "b.drops += 7\n"
        "print(j.drops, b.drops, Jar.label(2), j.label(3))\n"
    ),
    "dunder": (
        "class Log:\n"
        "    def __init__(self, length):\n"
        "        self.length = length\n"
        "    def __repr__(self):\n"
        "        return f'Log({self.length})'\n"
        "    def __lt__(self, other):\n"
        "        return self.length < other.length\n"
        "    def __eq__(self, other):\n"
        "        return self.length == other.length\n"
        "    def __len__(self):\n"
        "        return self.length\n"
        "logs = [Log(3), Log(1), Log(2)]\n"
        "print(sorted(logs), len(logs[0]), Log(1) == Log(1), Log(1) in logs)\n"
    ),
    "dataclass": (
        "from dataclasses import dataclass, field, asdict\n"
        "@dataclass\n"
        "class Log:\n"
        "    kind: str\n"
        "    length: float = 2.5\n"
        "    tags: list = field(default_factory=list)\n"
        "    def __post_init__(self):\n"
        "        self.kind = self.kind.lower()\n"
        "@dataclass(frozen=True, order=True)\n"
        "class Point:\n"
        "    x: int\n"
        "    y: int = 0\n"
        "a = Log('OAK')\n"
        "print(a, asdict(a))\n"
        "print(sorted([Point(2, 1), Point(1, 5)]), Point(1) == Point(1, 0))\n"
        "p = Point(1, 2)\n"
        "try:\n"
        "    p.x = 5\n"
        "except AttributeError:\n"
        "    print('frozen')\n"
    ),
    "namedtuple": (
        "from typing import NamedTuple\n"
        "class Paw(NamedTuple):\n"
        "    kind: str\n"
        "    size: int = 1\n"
        "    def big(self):\n"
        "        return self.size > 2\n"
        "p = Paw('fox', 3)\n"
        "kind, size = p\n"
        "print(p, p.big(), kind, size, p[0], p._replace(size=1))\n"
    ),
    "own_exceptions": (
        "class RainError(Exception):\n"
        "    def __init__(self, drops):\n"
        "        super().__init__(f'{drops} drops')\n"
        "        self.drops = drops\n"
        "try:\n"
        "    raise RainError(5)\n"
        "except RainError as e:\n"
        "    print('rain', e.drops, e)\n"
    ),
    "decorators": (
        "def sneaky(move):\n"
        "    def quiet(*args, **kwargs):\n"
        "        print('shh')\n"
        "        return move(*args, **kwargs)\n"
        "    return quiet\n"
        "def times(n):\n"
        "    def decorate(func):\n"
        "        def again(*args):\n"
        "            for _ in range(n):\n"
        "                func(*args)\n"
        "        return again\n"
        "    return decorate\n"
        "@times(2)\n"
        "@sneaky\n"
        "def hop(height, where='up'):\n"
        "    print('hop', height, where)\n"
        "hop(3)\n"
    ),
    "wraps_and_cache": (
        "import functools\n"
        "def logged(func):\n"
        "    @functools.wraps(func)\n"
        "    def inner(*args):\n"
        "        return func(*args)\n"
        "    return inner\n"
        "@logged\n"
        "def dig():\n"
        "    return 1\n"
        "print(dig.__name__)\n"
        "@functools.cache\n"
        "def fib(n):\n"
        "    return n if n < 2 else fib(n - 1) + fib(n - 2)\n"
        "print(fib(30))\n"
    ),
    "class_decorator": (
        "class count_calls:\n"
        "    def __init__(self, func):\n"
        "        self.func = func\n"
        "        self.calls = 0\n"
        "    def __call__(self, *args):\n"
        "        self.calls += 1\n"
        "        return self.func(*args)\n"
        "@count_calls\n"
        "def hello(name):\n"
        "    return 'hi ' + name\n"
        "print(hello('a'), hello('b'), hello.calls)\n"
    ),
    "closures_nonlocal": (
        "def counter():\n"
        "    count = 0\n"
        "    def tick():\n"
        "        nonlocal count\n"
        "        count += 1\n"
        "        return count\n"
        "    return tick\n"
        "t = counter()\n"
        "t()\n"
        "print(t(), t())\n"
    ),
    "star_args": (
        "def f(a, *rest, key=0, **more):\n"
        "    print(a, rest, key, sorted(more.items()))\n"
        "f(1, 2, 3, key=4, x=5)\n"
        "args = [1, 2]\n"
        "opts = {'key': 9}\n"
        "f(*args, **opts)\n"
        "print(*'abc', sep='-')\n"
    ),
    "with_open": (
        "with open('scores.txt', 'w') as f:\n"
        "    f.write('Momo 3\\n')\n"
        "    f.write('Bea 5\\n')\n"
        "with open('scores.txt', 'a') as f:\n"
        "    f.write('Ola 4\\n')\n"
        "with open('scores.txt') as f:\n"
        "    for line in f:\n"
        "        name, score = line.split()\n"
        "        print(name, int(score) * 2)\n"
        "try:\n"
        "    open('missing.txt')\n"
        "except FileNotFoundError:\n"
        "    print('no file')\n"
    ),
    "with_own_context": (
        "class Basket:\n"
        "    def __enter__(self):\n"
        "        print('take basket')\n"
        "        return self\n"
        "    def __exit__(self, kind, value, tb):\n"
        "        print('put back', kind is not None)\n"
        "        return True\n"
        "with Basket() as b:\n"
        "    print('picking')\n"
        "    raise ValueError('oops')\n"
        "print('after')\n"
    ),
    "match": (
        "def react(footprint):\n"
        "    match footprint:\n"
        "        case ('paw', size) if size > 2:\n"
        "            return f'hide from a big paw {size}'\n"
        "        case ('paw', _) | ('claw', _):\n"
        "            return 'small animal'\n"
        "        case ('boot', *rest):\n"
        "            return f'run {rest}'\n"
        "        case {'kind': kind, **others}:\n"
        "            return f'map {kind} {others}'\n"
        "        case int(n) | float(n):\n"
        "            return f'number {n}'\n"
        "        case None:\n"
        "            return 'nothing'\n"
        "        case _:\n"
        "            return 'keep sniffing'\n"
        "for f in [('paw', 3), ('paw', 1), ('boot', 1, 2), {'kind': 'x', 'a': 1},"
        " 4.5, None, 'z']:\n"
        "    print(react(f))\n"
    ),
    "match_class": (
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Track:\n"
        "    kind: str\n"
        "    size: int\n"
        "for t in [Track('paw', 3), Track('boot', 9)]:\n"
        "    match t:\n"
        "        case Track('paw', size=s):\n"
        "            print('paw', s)\n"
        "        case Track(kind=k):\n"
        "            print('other', k)\n"
    ),
    "asyncio_gather": (
        "import asyncio\n"
        "async def arm(n, delay):\n"
        "    print('reach', n)\n"
        "    await asyncio.sleep(delay)\n"
        "    print('got', n)\n"
        "    return n * 10\n"
        "async def main():\n"
        "    results = await asyncio.gather(arm(1, 0.03), arm(2, 0.01), arm(3, 0.02))\n"
        "    print(results)\n"
        "asyncio.run(main())\n"
    ),
    "asyncio_tasks_and_race": (
        "import asyncio\n"
        "shells = 0\n"
        "async def gather_shell():\n"
        "    global shells\n"
        "    seen = shells\n"
        "    await asyncio.sleep(0)\n"
        "    shells = seen + 1\n"
        "async def main():\n"
        "    tasks = [asyncio.create_task(gather_shell()) for _ in range(4)]\n"
        "    for task in tasks:\n"
        "        await task\n"
        "    print('shells', shells)\n"
        "asyncio.run(main())\n"
    ),
    "asyncio_lock": (
        "import asyncio\n"
        "shells = 0\n"
        "lock = None\n"
        "async def gather_shell():\n"
        "    global shells\n"
        "    async with lock:\n"
        "        seen = shells\n"
        "        await asyncio.sleep(0)\n"
        "        shells = seen + 1\n"
        "async def main():\n"
        "    global lock\n"
        "    lock = asyncio.Lock()\n"
        "    await asyncio.gather(*[gather_shell() for _ in range(4)])\n"
        "    print('shells', shells)\n"
        "asyncio.run(main())\n"
    ),
    "asyncio_queue": (
        "import asyncio\n"
        "async def producer(q):\n"
        "    for i in range(3):\n"
        "        await q.put(i)\n"
        "        await asyncio.sleep(0.01)\n"
        "    await q.put(None)\n"
        "async def consumer(q):\n"
        "    while True:\n"
        "        item = await q.get()\n"
        "        if item is None:\n"
        "            break\n"
        "        print('ate', item)\n"
        "async def main():\n"
        "    q = asyncio.Queue()\n"
        "    await asyncio.gather(producer(q), consumer(q))\n"
        "asyncio.run(main())\n"
    ),
    "taskgroup_and_except_star": (
        "import asyncio\n"
        "class RainError(Exception):\n"
        "    pass\n"
        "async def arm(n):\n"
        "    await asyncio.sleep(0.1 * n)\n"
        "    if n == 2:\n"
        "        raise RainError('wet')\n"
        "    print('done', n)\n"
        "async def main():\n"
        "    try:\n"
        "        async with asyncio.TaskGroup() as group:\n"
        "            group.create_task(arm(1))\n"
        "            group.create_task(arm(2))\n"
        "            group.create_task(arm(3))\n"
        "    except* RainError as errors:\n"
        "        print('rain', len(errors.exceptions))\n"
        "asyncio.run(main())\n"
    ),
    "async_return_and_await_in_expression": (
        "import asyncio\n"
        "async def double(n):\n"
        "    await asyncio.sleep(0)\n"
        "    return n * 2\n"
        "async def main():\n"
        "    total = await double(1) + await double(2)\n"
        "    print(total, [await double(3)][0] if True else 0)\n"
        "    if await double(0) == 0:\n"
        "        print('zero')\n"
        "asyncio.run(main())\n"
    ),
    "input_and_name": (
        "name = input('Name? ')\nprint('Hi', name)\nif __name__ == '__main__':\n    print('main')\n"
    ),
    "itertools_math_random": (
        "import itertools\n"
        "import math\n"
        "print(list(itertools.islice(itertools.count(5), 3)), math.sqrt(16), math.factorial(5))\n"
        "print(list(itertools.chain('ab', [1])), list(itertools.pairwise([1, 2, 3])))\n"
        "import functools\n"
        "print(functools.reduce(lambda a, b: a + b, [1, 2, 3]))\n"
    ),
}

INPUTS = {"input_and_name": "Momo\n"}


def cpython(source, folder, stdin=""):
    """Real Python, in a folder of its own: programs that open() files write real ones."""
    return subprocess.run(
        [sys.executable, "-I", "-c", source],
        capture_output=True,
        text=True,
        timeout=30,
        input=stdin,
        cwd=folder,
    )


def ours(source, **kwargs):
    parsed = parse(source)
    assert parsed.ok, parsed.diagnostics
    assert not [d for d in parsed.diagnostics if d.severity == "warning"], parsed.diagnostics
    return parsed, run(parsed.program, **kwargs)


@pytest.mark.parametrize("name", PROGRAMS)
def test_same_output_as_cpython(name, tmp_path):
    source = PROGRAMS[name]
    stdin = INPUTS.get(name, "")
    expected = cpython(source, tmp_path, stdin)
    assert expected.returncode == 0, expected.stderr
    _, result = ours(source, inputs=stdin.splitlines())
    assert result.error is None, result.error.message
    assert result.output == expected.stdout.splitlines()


@pytest.mark.parametrize("name", PROGRAMS)
def test_round_trip(name):
    first = parse(PROGRAMS[name])
    text = print_program(first.program).text
    second = parse(text)
    assert second.ok
    assert ir.to_dict(first.program, ids=False) == ir.to_dict(second.program, ids=False)


def test_endless_generator_is_stopped_by_the_step_limit():
    _, result = ours("def forever():\n    while True:\n        yield 1\nprint(list(forever()))\n")
    assert isinstance(result.error, LearnerError)
    assert result.error.kind == "too_many_steps"


def test_endless_iterator_is_stopped_by_the_item_limit():
    _, result = ours("import itertools\nprint(list(itertools.count()))\n")
    assert result.error is not None and "itertools.count()" in result.error.message


def test_classes_cannot_hook_into_the_interpreter():
    _, result = ours("class Sneaky:\n    def __getattribute__(self, name):\n        return 1\n")
    assert "can't define `__getattribute__`" in result.error.message
    _, result = ours("class A:\n    pass\nprint(A().__class__)\n")
    assert "keeps `__class__` to itself" in result.error.message
    _, result = ours("t = type(5)\nm = type(t)\nm('X', (), {})\n")
    assert "can't make new" in result.error.message


def test_await_outside_async_def_is_explained():
    _, result = ours("import asyncio\nawait asyncio.sleep(1)\n")
    assert "only works inside an `async def`" in result.error.message


def test_never_awaited_coroutine_leaves_a_note():
    _, result = ours("async def main():\n    print('hi')\nmain()\n")
    assert result.error is None
    assert any(s.note and "never ran" in s.note for s in result.steps)


def test_async_steps_have_lanes_and_simulated_time():
    source = PROGRAMS["asyncio_gather"]
    _, result = ours(source)
    assert result.lanes[0] == "main"
    assert {"arm(1, 0.03)", "arm(2, 0.01)", "arm(3, 0.02)"} <= set(result.lanes)
    assert result.time == pytest.approx(0.03)
    first = next(i for i, step in enumerate(result.steps) if step.lane is not None)
    assert all(step.lane is not None for step in result.steps[first:])


def test_thread_race_is_repeatable_and_a_lock_fixes_it():
    race = (
        "import threading\n"
        "shells = 0\n"
        "def gather():\n"
        "    global shells\n"
        "    for _ in range(3):\n"
        "        seen = shells\n"
        "        shells = seen + 1\n"
        "arms = [threading.Thread(target=gather) for _ in range(4)]\n"
        "for arm in arms:\n"
        "    arm.start()\n"
        "for arm in arms:\n"
        "    arm.join()\n"
        "print(shells)\n"
    )
    first = ours(race)[1]
    again = ours(race)[1]
    assert first.error is None
    assert first.output == again.output
    assert int(first.output[0]) < 12  # some updates got lost
    fixed = race.replace(
        "        seen = shells\n        shells = seen + 1\n",
        "        with lock:\n            seen = shells\n            shells = seen + 1\n",
    ).replace("shells = 0\n", "shells = 0\nlock = threading.Lock()\n", 1)
    result = ours(fixed)[1]
    assert result.error is None, result.error
    assert result.output == ["12"]


def test_free_threading_overlaps_threads():
    source = (
        "import threading\n"
        "def work():\n"
        "    for _ in range(5):\n"
        "        pass\n"
        "        x = 1\n"
        "ts = [threading.Thread(target=work) for _ in range(4)]\n"
        "for t in ts:\n"
        "    t.start()\n"
        "for t in ts:\n"
        "    t.join()\n"
    )
    with_gil = ours(source)[1]
    without = ours(source, gil=False)[1]
    assert with_gil.error is None and without.error is None
    assert without.time * 3 < with_gil.time


def test_newer_builtins_and_syntax_name_their_release():
    result = parse("type Stack = list[int]\n", (3, 11))
    assert not result.ok
    assert "Python 3.12" in result.errors[0].message
    parsed = parse("x = frozendict(a=1)\n")
    outcome = run(parsed.program, version=(3, 13))
    assert "`frozendict` arrived in Python 3.15" in outcome.error.message
    outcome = run(parse("import itertools\nitertools.batched([1], 1)\n").program, version=(3, 11))
    assert "`itertools.batched` arrived in Python 3.12" in outcome.error.message
