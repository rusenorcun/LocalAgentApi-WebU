import asyncio
from server.database import Base, engine

async def f():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(f())
