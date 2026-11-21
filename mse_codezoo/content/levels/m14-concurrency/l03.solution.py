import asyncio

async def main():
    arms = [asyncio.create_task(reach(arm)) for arm in range(8)]
    for arm in arms:
        await arm

asyncio.run(main())
