"""Comprehensive verification script for User, Society, Block, and Flat models."""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from app.core.db import engine, AsyncSessionLocal
from app.models.user import User, RoleEnum
from app.models.society import Society, Block, Flat, OccupancyStatusEnum


async def verify_schema():
    print("=== Step 1: Inspecting Database Schema in PostgreSQL ===")
    async with engine.connect() as conn:
        # Check tables
        tables_res = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
        )
        tables = [row[0] for row in tables_res.fetchall()]
        print(f"Tables present: {tables}")
        assert "users" in tables, "users table missing"
        assert "societies" in tables, "societies table missing"
        assert "blocks" in tables, "blocks table missing"
        assert "flats" in tables, "flats table missing"

        # Check pgcrypto extension
        ext_res = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'"))
        ext = ext_res.scalar()
        print(f"pgcrypto extension installed: {ext == 'pgcrypto'}")

        # Check unique constraint on flats (block_id, unit_number)
        uq_res = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'flats'::regclass AND contype = 'u'"
            )
        )
        uq_constraints = [row[0] for row in uq_res.fetchall()]
        print(f"Flats unique constraints: {uq_constraints}")
        assert "uq_block_unit_number" in uq_constraints, "uq_block_unit_number constraint missing"

        # Check foreign keys and cascade rules
        fk_res = await conn.execute(
            text(
                "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, rc.delete_rule "
                "FROM information_schema.table_constraints AS tc "
                "JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints AS rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'"
            )
        )
        fks = fk_res.fetchall()
        for fk in fks:
            print(f"FK: {fk[0]}.{fk[1]} -> {fk[2]} (on_delete={fk[3]})")


async def verify_orm_roundtrip():
    print("\n=== Step 2: Testing ORM Model Creation & Relationship Traversal ===")
    test_user_id = None
    test_society_id = None
    test_block_id = None
    test_flat_id = None

    async with AsyncSessionLocal() as session:
        # 1. Create User
        test_user = User(
            email="test.society.admin@example.com",
            phone="+919999988888",
            hashed_password="mock_hashed_password_for_verification",
            role=RoleEnum.admin,
            is_active=True,
        )
        session.add(test_user)
        await session.flush()
        test_user_id = test_user.id
        print(f"Created Test User: id={test_user.id}, role={test_user.role.value}")
        assert test_user.id is not None, "Server default UUID failed for User"

        # 2. Create Society
        test_society = Society(
            name="Greenwood Heights Residencies",
            address="Plot 42, Sector 15, Cyber City",
            latitude=Decimal("12.9715987"),
            longitude=Decimal("77.5945627"),
            rwa_license_number="RWA/2026/BLR/0042",
            admin_id=test_user.id,
            response_window_seconds=120,
        )
        session.add(test_society)
        await session.flush()
        test_society_id = test_society.id
        print(f"Created Test Society: id={test_society.id}, name='{test_society.name}'")
        assert test_society.id is not None, "Server default UUID failed for Society"

        # 3. Create Block
        test_block = Block(
            name="Tower A - Oak",
            society_id=test_society.id,
        )
        session.add(test_block)
        await session.flush()
        test_block_id = test_block.id
        print(f"Created Test Block: id={test_block.id}, name='{test_block.name}'")
        assert test_block.id is not None, "Server default UUID failed for Block"

        # 4. Create Flat
        test_flat = Flat(
            unit_number="1001",
            floor=10,
            block_id=test_block.id,
            occupancy_status=OccupancyStatusEnum.owner,
        )
        session.add(test_flat)
        await session.flush()
        test_flat_id = test_flat.id
        print(f"Created Test Flat: id={test_flat.id}, unit='{test_flat.unit_number}', status={test_flat.occupancy_status.value}")
        assert test_flat.id is not None, "Server default UUID failed for Flat"

        await session.commit()

    print("\n=== Step 3: Querying Back via ORM Relationships ===")
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Society)
            .where(Society.id == test_society_id)
            .options(
                selectinload(Society.blocks).selectinload(Block.flats),
                selectinload(Society.admin),
            )
        )
        res = await session.execute(stmt)
        fetched_society = res.scalar_one()

        print(f"Fetched Society: {fetched_society.name}")
        print(f"  Admin Email: {fetched_society.admin.email} (Role: {fetched_society.admin.role.value})")
        assert fetched_society.admin.id == test_user_id
        assert len(fetched_society.blocks) == 1

        block = fetched_society.blocks[0]
        print(f"  Block: {block.name} (ID: {block.id})")
        assert block.id == test_block_id
        assert len(block.flats) == 1

        flat = block.flats[0]
        print(f"    Flat: Unit {flat.unit_number}, Floor {flat.floor}, Status: {flat.occupancy_status.value}")
        assert flat.id == test_flat_id
        assert flat.occupancy_status == OccupancyStatusEnum.owner

        print("All ORM relationship traversals verified successfully!")

    print("\n=== Step 4: Cleaning Up Test Data ===")
    async with AsyncSessionLocal() as session:
        # Delete society (should cascade delete block and flat)
        stmt = select(Society).where(Society.id == test_society_id)
        soc = (await session.execute(stmt)).scalar_one_or_none()
        if soc:
            await session.delete(soc)

        # Delete admin user
        stmt_user = select(User).where(User.id == test_user_id)
        usr = (await session.execute(stmt_user)).scalar_one_or_none()
        if usr:
            await session.delete(usr)

        await session.commit()

    # Confirm clean database
    async with AsyncSessionLocal() as session:
        rem_users = (await session.execute(select(User).where(User.id == test_user_id))).fetchall()
        rem_societies = (await session.execute(select(Society).where(Society.id == test_society_id))).fetchall()
        rem_blocks = (await session.execute(select(Block).where(Block.id == test_block_id))).fetchall()
        rem_flats = (await session.execute(select(Flat).where(Flat.id == test_flat_id))).fetchall()

        print(f"Remaining test rows: Users={len(rem_users)}, Societies={len(rem_societies)}, Blocks={len(rem_blocks)}, Flats={len(rem_flats)}")
        assert len(rem_users) == 0 and len(rem_societies) == 0 and len(rem_blocks) == 0 and len(rem_flats) == 0
        print("Database is completely clean. Verification passed!")


async def main():
    await verify_schema()
    await verify_orm_roundtrip()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
