"""初始化数据库 — 建表 + 灌入Mock数据"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import engine, AsyncSessionLocal
from app.models import Base
from app.mock.generator import generate_all_mock_data
from app.mock.semantic_seed import seed_semantic_yaml_definitions


async def main():
    print("=== TDA-TDP database init ===")

    # 1. Create tables
    print("\n1. Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("   [OK] 28 tables created")

    # 2. Seed mock data
    print("\n2. Seeding mock data...")
    async with AsyncSessionLocal() as session:
        await generate_all_mock_data(session)
        await seed_semantic_yaml_definitions(session)
        await session.commit()

    print("\n=== Initialization completed ===")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
