import asyncio
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.db import engine, AsyncSessionLocal


async def verify():
    print("Testing app.core.db engine connectivity...")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        val = result.scalar()
        print(f"Engine Direct SELECT 1 OK: {val}")

    print("Testing AsyncSessionLocal session factory...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT current_database(), current_user"))
        db, user = result.fetchone()
        print(f"Session Factory OK -> Database: '{db}', User: '{user}'")

    await engine.dispose()
    print("Database engine verified successfully!")


if __name__ == "__main__":
    asyncio.run(verify())
