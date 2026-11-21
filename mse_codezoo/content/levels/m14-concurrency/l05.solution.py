import asyncio

async def picker(basket):
    for fruit in ["one", "two", "three"]:
        await basket.put(fruit)
        await asyncio.sleep(1)
    await basket.put(None)

async def eater(basket):
    while True:
        fruit = await basket.get()
        if fruit is None:
            break
        say(f"ate {fruit}")

async def main():
    basket = asyncio.Queue()
    await asyncio.gather(picker(basket), eater(basket))

asyncio.run(main())
