"""Verification script for ResidentProfile and GuardianLink models and constraints."""

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.core.db import engine, AsyncSessionLocal
from app.models.user import User, RoleEnum
from app.models.society import Society, Block, Flat, OccupancyStatusEnum
from app.models.resident import ResidentProfile, ResidentStatusEnum
from app.models.guardian_link import (
    GuardianLink,
    GuardianPriorityEnum,
    ConsentStatusEnum,
)


async def verify_schema():
    print("=== Step 1: Inspecting Schema, Constraints, & Indexes in PostgreSQL ===")
    async with engine.connect() as conn:
        # 1. Check foreign key rules
        fk_res = await conn.execute(
            text(
                "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, rc.delete_rule "
                "FROM information_schema.table_constraints AS tc "
                "JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints AS rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name IN ('resident_profiles', 'guardian_links') "
                "ORDER BY tc.table_name, kcu.column_name"
            )
        )
        fks = fk_res.fetchall()
        for fk in fks:
            print(f"FK: {fk[0]}.{fk[1]} -> {fk[2]} (on_delete={fk[3]})")
            if fk[0] == "resident_profiles" and fk[1] == "flat_id":
                assert fk[3] == "SET NULL", f"Expected SET NULL for flat_id, got {fk[3]}"
            if fk[0] == "resident_profiles" and fk[1] == "user_id":
                assert fk[3] == "CASCADE", f"Expected CASCADE for user_id, got {fk[3]}"
            if fk[0] == "guardian_links":
                assert fk[3] == "CASCADE", f"Expected CASCADE for guardian_link FK, got {fk[3]}"

        # 2. Check check constraints on guardian_links
        chk_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE conrelid = 'guardian_links'::regclass AND contype = 'c'"
            )
        )
        chks = chk_res.fetchall()
        for chk in chks:
            print(f"CheckConstraint: {chk[0]} -> {chk[1]}")
            assert "guardian_id <> resident_id" in chk[1] or "guardian_id != resident_id" in chk[1]

        # 3. Check partial unique index on guardian_links
        idx_res = await conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'guardian_links'"
            )
        )
        indexes = idx_res.fetchall()
        partial_idx_found = False
        for idx in indexes:
            print(f"Index: {idx[0]} -> {idx[1]}")
            if idx[0] == "uq_one_primary_guardian_per_resident":
                partial_idx_found = True
                assert "priority = 'primary'" in idx[1]
        assert partial_idx_found, "Partial unique index uq_one_primary_guardian_per_resident missing!"
        print("Schema constraints and indexes successfully verified!")


async def verify_constraints_and_orm():
    print("\n=== Step 2: Testing Integrity Constraints & Violations ===")

    # Setup base data (Society, Block, Flat, Resident User, Guardian Users)
    res_user_id = None
    g1_user_id = None
    g2_user_id = None
    flat_id = None
    soc_id = None

    async with AsyncSessionLocal() as session:
        # Admin / Resident user
        res_user = User(
            email="resident.alpha@example.com",
            phone="+919111111111",
            hashed_password="pw_hash_mock",
            role=RoleEnum.resident,
            is_active=True,
        )
        # Guardian 1
        g1_user = User(
            email="guardian.one@example.com",
            phone="+919222222222",
            hashed_password="pw_hash_mock",
            role=RoleEnum.guardian,
            is_active=True,
        )
        # Guardian 2
        g2_user = User(
            email="guardian.two@example.com",
            phone="+919333333333",
            hashed_password="pw_hash_mock",
            role=RoleEnum.guardian,
            is_active=True,
        )
        session.add_all([res_user, g1_user, g2_user])
        await session.flush()
        res_user_id = res_user.id
        g1_user_id = g1_user.id
        g2_user_id = g2_user.id

        # Society, Block, Flat
        soc = Society(
            name="Apex Horizon",
            address="100 Main St",
            latitude=Decimal("13.0826802"),
            longitude=Decimal("80.2707184"),
            admin_id=res_user.id,
            response_window_seconds=90,
        )
        session.add(soc)
        await session.flush()
        soc_id = soc.id

        blk = Block(name="Block 1", society_id=soc.id)
        session.add(blk)
        await session.flush()

        flt = Flat(unit_number="502", floor=5, block_id=blk.id, occupancy_status=OccupancyStatusEnum.owner)
        session.add(flt)
        await session.flush()
        flat_id = flt.id

        # Create valid ResidentProfile
        prof = ResidentProfile(
            user_id=res_user.id,
            flat_id=flt.id,
            date_of_birth=date(1990, 5, 20),
            status=ResidentStatusEnum.active,
        )
        session.add(prof)
        await session.commit()
        print("Base test entities committed successfully.")

    # Test 1: 1:1 constraint on ResidentProfile.user_id
    print("\n--- Test 1: Duplicate ResidentProfile for same user_id ---")
    async with AsyncSessionLocal() as session:
        try:
            duplicate_prof = ResidentProfile(
                user_id=res_user_id,
                flat_id=flat_id,
                status=ResidentStatusEnum.away,
            )
            session.add(duplicate_prof)
            await session.commit()
            raise AssertionError("FAIL: Allowed duplicate ResidentProfile for same user_id!")
        except IntegrityError:
            print("PASS: Database correctly rejected duplicate ResidentProfile (1:1 constraint enforced).")

    # Test 2: Primary Guardian Link + Duplicate Primary Guardian Link
    print("\n--- Test 2: Duplicate Primary Guardian for same resident ---")
    async with AsyncSessionLocal() as session:
        # Valid primary guardian
        link1 = GuardianLink(
            guardian_id=g1_user_id,
            resident_id=res_user_id,
            priority=GuardianPriorityEnum.primary,
            consent_status=ConsentStatusEnum.accepted,
        )
        session.add(link1)
        await session.commit()
        print("Created Primary GuardianLink with guardian 1.")

    async with AsyncSessionLocal() as session:
        try:
            # Second primary guardian (must fail via partial unique index)
            link2 = GuardianLink(
                guardian_id=g2_user_id,
                resident_id=res_user_id,
                priority=GuardianPriorityEnum.primary,
                consent_status=ConsentStatusEnum.pending,
            )
            session.add(link2)
            await session.commit()
            raise AssertionError("FAIL: Allowed two primary guardians for same resident!")
        except IntegrityError:
            print("PASS: Database correctly rejected second primary guardian (partial unique index enforced).")

    # Test 3: Multiple Secondary Guardians (Must Succeed)
    print("\n--- Test 3: Secondary Guardian Link (Allowed) ---")
    async with AsyncSessionLocal() as session:
        link_sec = GuardianLink(
            guardian_id=g2_user_id,
            resident_id=res_user_id,
            priority=GuardianPriorityEnum.secondary,
            consent_status=ConsentStatusEnum.pending,
        )
        session.add(link_sec)
        await session.commit()
        print("PASS: Successfully added secondary guardian alongside primary guardian.")

    # Test 4: Self-Guardian Check Constraint
    print("\n--- Test 4: Self-Guardian (guardian_id == resident_id) ---")
    async with AsyncSessionLocal() as session:
        try:
            self_link = GuardianLink(
                guardian_id=res_user_id,
                resident_id=res_user_id,
                priority=GuardianPriorityEnum.secondary,
            )
            session.add(self_link)
            await session.commit()
            raise AssertionError("FAIL: Allowed user to be their own guardian!")
        except IntegrityError:
            print("PASS: Database correctly rejected self-guardian (CheckConstraint enforced).")

    # Test 5: ON DELETE SET NULL on Flat deletion
    print("\n--- Test 5: Flat Deletion preserves ResidentProfile (flat_id -> NULL) ---")
    async with AsyncSessionLocal() as session:
        flt_obj = (await session.execute(select(Flat).where(Flat.id == flat_id))).scalar_one()
        await session.delete(flt_obj)
        await session.commit()

    async with AsyncSessionLocal() as session:
        prof_obj = (await session.execute(select(ResidentProfile).where(ResidentProfile.user_id == res_user_id))).scalar_one_or_none()
        assert prof_obj is not None, "ResidentProfile was unexpectedly deleted!"
        assert prof_obj.flat_id is None, f"Expected flat_id to be NULL, got {prof_obj.flat_id}"
        print(f"PASS: ResidentProfile preserved after flat deletion with flat_id={prof_obj.flat_id}")

    # Test 6: Cleanup & CASCADE test on User deletion
    print("\n--- Test 6: User Deletion cascades to Profile & Links ---")
    async with AsyncSessionLocal() as session:
        # Delete society first (due to admin_id FK)
        soc_obj = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one_or_none()
        if soc_obj:
            await session.delete(soc_obj)

        # Delete users
        for uid in [res_user_id, g1_user_id, g2_user_id]:
            u = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if u:
                await session.delete(u)
        await session.commit()

    async with AsyncSessionLocal() as session:
        rem_profs = (await session.execute(select(ResidentProfile).where(ResidentProfile.user_id == res_user_id))).fetchall()
        rem_links = (await session.execute(select(GuardianLink).where(GuardianLink.resident_id == res_user_id))).fetchall()
        rem_users = (await session.execute(select(User).where(User.id.in_([res_user_id, g1_user_id, g2_user_id])))).fetchall()
        print(f"Remaining: Profiles={len(rem_profs)}, Links={len(rem_links)}, Users={len(rem_users)}")
        assert len(rem_profs) == 0 and len(rem_links) == 0 and len(rem_users) == 0
        print("PASS: Cascades verified and all test rows cleaned up completely.")


async def main():
    await verify_schema()
    await verify_constraints_and_orm()
    await engine.dispose()
    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
