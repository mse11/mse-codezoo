import asyncio

basket = 0
lock = asyncio.Lock()

async def fetch(arm):
    global basket
    found = await reach(arm)
    if found:
        async with lock:
            count = basket
            await asyncio.sleep(0)
            basket = count + 1

async def main():
    arms = [arm for arm in range(8) if arm != 0]
    await asyncio.gather(*[fetch(arm) for arm in arms])
    say(f"{basket} shells")

asyncio.run(main())
