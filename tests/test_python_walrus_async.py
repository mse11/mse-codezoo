"""`:=`, `async for` and async generators: parsed, printed back, run, and compared with
CPython (they used to stay raw code)."""

import subprocess
import sys

import pytest

from mse_codezoo.interpreter import run
from mse_codezoo.lang_python import parse, print_program

ASYNC_FISH = """import asyncio


async def fish(n):
    for i in range(n):
        await asyncio.sleep(1)
        yield i * 10


async def main():
    async for f in fish(3):
        print(f)
    total = 0
    async for f in fish(4):
        if f > 10:
            break
        total += f
    print("total", total)


asyncio.run(main())
"""

TWO_TASKS = """import asyncio


async def ticks(name, n):
    for i in range(n):
        await asyncio.sleep(1)
        yield f"{name}{i}"


async def listen(name):
    async for word in ticks(name, 2):
        print(word)


async def main():
    await asyncio.gather(listen("a"), listen("b"))


asyncio.run(main())
"""

WALRUS = """fish = [3, 1, 4, 1, 5]
if (n := len(fish)) > 3:
    print("many", n)
big = [y for x in fish if (y := x * 2) > 4]
print(big)
total = 0
items = list(fish)
while (item := items.pop() if items else None) is not None:
    total += item
print(total, item)
"""


def cpython(source):
    return subprocess.run(
        [sys.executable, "-I", "-c", source], capture_output=True, text=True, timeout=30
    )


@pytest.mark.parametrize(
    "source", [ASYNC_FISH, TWO_TASKS, WALRUS], ids=["async-for", "tasks", "walrus"]
)
def test_same_output_as_cpython(source):
    parsed = parse(source)
    assert parsed.ok and not parsed.diagnostics, parsed.diagnostics
    result = run(parsed.program)
    assert result.ok, result.error and result.error.message
    expected = cpython(source)
    assert expected.returncode == 0, expected.stderr
    assert result.output == expected.stdout.splitlines()


def test_an_async_generator_waits_on_the_simulated_clock():
    result = run(parse(ASYNC_FISH).program)
    assert result.time == 6.0  # 3 sleeps, then 3 more until the value 20 breaks the loop


@pytest.mark.parametrize(
    "source",
    [
        "if (n := len([1, 2])) > 1:\n    print(n)\n",
        "while x := 0:\n    pass\n",
        "(y := 5)\n",
        "z = (w := 3)\n",
        "print(v := 2)\n",
        "async def main():\n    async for f in fish():\n        print(f)\n",
    ],
)
def test_they_parse_and_print_back(source):
    result = parse(source)
    assert result.ok and not result.diagnostics, result.diagnostics
    assert print_program(result.program).text == source


def test_kind_messages():
    outside = run(parse("async for x in y:\n    pass\n").program)
    assert "only works inside an `async def`" in outside.error.message
    not_async = run(
        parse(
            "import asyncio\n\n\nasync def main():\n"
            "    async for x in [1, 2]:\n        print(x)\n\n\nasyncio.run(main())\n"
        ).program
    )
    assert "needs an async generator" in not_async.error.message
