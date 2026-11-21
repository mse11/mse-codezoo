import asyncio

async def main():
    await asyncio.gather(reach(0), reach(2), reach(4), reach(6))

asyncio.run(main())
