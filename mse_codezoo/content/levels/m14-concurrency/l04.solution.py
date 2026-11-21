import asyncio

shells = 0
lock = asyncio.Lock()

async def count_shell():
    global shells
    async with lock:
        seen = shells
        await asyncio.sleep(0)
        shells = seen + 1

async def main():
    await asyncio.gather(*[count_shell() for _ in range(8)])
    say(shells)

asyncio.run(main())
