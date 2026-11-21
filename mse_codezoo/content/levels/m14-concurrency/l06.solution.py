import asyncio

class StungError(Exception):
    pass

async def careful(arm):
    found = await reach(arm)
    if found == "jellyfish":
        raise StungError(f"arm {arm}")

async def main():
    try:
        async with asyncio.TaskGroup() as group:
            for arm in range(5):
                group.create_task(careful(arm))
    except* StungError as stung:
        say(f"ouch: {len(stung.exceptions)}")

asyncio.run(main())
