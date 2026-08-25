"""Verification script for VolunteerProfile, SecurityProfile, and EmergencyContact models."""

import asyncio
import sys
from datetime import time
from decimal import Decimal
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text, delete
from sqlalchemy.exc import IntegrityError
from app.core.db import engine, AsyncSessionLocal
from app.models.user import User, RoleEnum
from app.models.society import Society, Block
from app.models.volunteer import VolunteerProfile, VolunteerAvailabilityEnum
from app.models.security_staff import SecurityProfile
from app.models.emergency_contact import (
    EmergencyContact,
    ContactTypeEnum,
    ContactVerificationStatusEnum,
)

TEST_EMAILS = [
    "admin.soc1@example.com",
    "admin.soc2@example.com",
    "volunteer.jane@example.com",
    "sec.guard1@example.com",
    "sec.guard2@example.com",
    "sec.guard3@example.com",
    "resident.bob@example.com",
]


async def clean_test_data():
    async with AsyncSessionLocal() as session:
        # Fetch test users
        users = (await session.execute(select(User).where(User.email.in_(TEST_EMAILS)))).scalars().all()
        user_ids = [u.id for u in users]
        if user_ids:
            # Delete societies administered by these users
            socs = (await session.execute(select(Society).where(Society.admin_id.in_(user_ids)))).scalars().all()
            for s in socs:
                await session.delete(s)
            for u in users:
                await session.delete(u)
            await session.commit()


async def verify_schema():
    print("=== Step 1: Inspecting Schema, Types, and Constraints in PostgreSQL ===")
    async with engine.connect() as conn:
        # Check tables present
        tables_res = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN ('volunteer_profiles', 'security_profiles', 'emergency_contacts') "
                "ORDER BY table_name"
            )
        )
        tables = [row[0] for row in tables_res.fetchall()]
        print(f"Tables verified: {tables}")
        assert len(tables) == 3

        # Check column type of volunteer_profiles.skills
        col_res = await conn.execute(
            text(
                "SELECT column_name, data_type, udt_name "
                "FROM information_schema.columns "
                "WHERE table_name = 'volunteer_profiles' AND column_name = 'skills'"
            )
        )
        col = col_res.fetchone()
        print(f"volunteer_profiles.skills type: data_type={col[1]}, udt_name={col[2]}")
        assert col[1] == "ARRAY" and col[2] == "_varchar", f"Expected ARRAY of varchar, got {col}"

        # Check foreign keys and delete rules
        fk_res = await conn.execute(
            text(
                "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name, rc.delete_rule "
                "FROM information_schema.table_constraints AS tc "
                "JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints AS rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name IN ('volunteer_profiles', 'security_profiles', 'emergency_contacts') "
                "ORDER BY tc.table_name, kcu.column_name"
            )
        )
        fks = fk_res.fetchall()
        for fk in fks:
            print(f"FK: {fk[0]}.{fk[1]} -> {fk[2]} (on_delete={fk[3]})")
            if fk[0] == "security_profiles" and fk[1] == "assigned_block_id":
                assert fk[3] == "SET NULL", f"Expected SET NULL for assigned_block_id, got {fk[3]}"

        # Check composite unique constraint on security_profiles(society_id, employee_id)
        uq_res = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'security_profiles'::regclass AND contype = 'u'"
            )
        )
        uqs = [row[0] for row in uq_res.fetchall()]
        print(f"security_profiles unique constraints: {uqs}")
        assert "uq_society_employee_id" in uqs, "Composite constraint uq_society_employee_id missing"

        # Check enum values for contact_verification_status_enum
        enum_res = await conn.execute(
            text(
                "SELECT e.enumlabel "
                "FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid "
                "WHERE t.typname = 'contact_verification_status_enum' "
                "ORDER BY e.enumsortorder"
            )
        )
        enum_vals = [row[0] for row in enum_res.fetchall()]
        print(f"contact_verification_status_enum values: {enum_vals}")
        assert enum_vals == ["unverified", "pending", "verified"], f"Unexpected enum values: {enum_vals}"

        print("Schema and constraint inspection passed successfully!")


async def verify_models_behavior():
    print("\n=== Step 2: Testing Model Defaults, Constraints, and Scoped Uniqueness ===")

    await clean_test_data()

    u_admin1_id = None
    u_admin2_id = None
    u_vol_id = None
    u_sec1_id = None
    u_sec2_id = None
    u_sec3_id = None
    u_res_id = None
    soc1_id = None
    soc2_id = None

    try:
        async with AsyncSessionLocal() as session:
            # Create Admins and Societies
            admin1 = User(email="admin.soc1@example.com", phone="+919444444441", hashed_password="pw", role=RoleEnum.admin)
            admin2 = User(email="admin.soc2@example.com", phone="+919444444442", hashed_password="pw", role=RoleEnum.admin)
            session.add_all([admin1, admin2])
            await session.flush()
            u_admin1_id, u_admin2_id = admin1.id, admin2.id

            soc1 = Society(name="Palm Grove", address="Road 1", latitude=Decimal("12.91"), longitude=Decimal("77.61"), admin_id=admin1.id)
            soc2 = Society(name="Cedar Woods", address="Road 2", latitude=Decimal("12.92"), longitude=Decimal("77.62"), admin_id=admin2.id)
            session.add_all([soc1, soc2])
            await session.flush()
            soc1_id, soc2_id = soc1.id, soc2.id

            # Create Block in soc1
            blk1 = Block(name="Block North", society_id=soc1.id)
            session.add(blk1)
            await session.flush()

            # Create Volunteer User
            vol_user = User(email="volunteer.jane@example.com", phone="+919555555551", hashed_password="pw", role=RoleEnum.volunteer)
            # Create Security Users
            sec1_user = User(email="sec.guard1@example.com", phone="+919666666661", hashed_password="pw", role=RoleEnum.security)
            sec2_user = User(email="sec.guard2@example.com", phone="+919666666662", hashed_password="pw", role=RoleEnum.security)
            sec3_user = User(email="sec.guard3@example.com", phone="+919666666663", hashed_password="pw", role=RoleEnum.security)
            # Create Resident User
            res_user = User(email="resident.bob@example.com", phone="+919777777771", hashed_password="pw", role=RoleEnum.resident)

            session.add_all([vol_user, sec1_user, sec2_user, sec3_user, res_user])
            await session.flush()
            u_vol_id = vol_user.id
            u_sec1_id, u_sec2_id, u_sec3_id = sec1_user.id, sec2_user.id, sec3_user.id
            u_res_id = res_user.id
            await session.commit()

        # Test 1: VolunteerProfile defaults to off_duty, rating is None, skills is array
        print("\n--- Test 1: VolunteerProfile default availability_status == off_duty and rating is None ---")
        async with AsyncSessionLocal() as session:
            vol_prof = VolunteerProfile(
                user_id=u_vol_id,
                society_id=soc1_id,
                skills=["first_aid", "cpr", "fire_safety"],
                # availability_status left unassigned to verify default
            )
            session.add(vol_prof)
            await session.commit()

        async with AsyncSessionLocal() as session:
            fetched_vol = (await session.execute(select(VolunteerProfile).where(VolunteerProfile.user_id == u_vol_id))).scalar_one()
            print(f"Volunteer Profile: skills={fetched_vol.skills}, availability_status={fetched_vol.availability_status.value}, rating={fetched_vol.rating}")
            assert fetched_vol.availability_status == VolunteerAvailabilityEnum.off_duty, "Expected availability_status to default to 'off_duty'"
            assert fetched_vol.rating is None, "Expected rating to be None"
            assert fetched_vol.background_verified is False, "Expected background_verified to default to False"
            assert fetched_vol.skills == ["first_aid", "cpr", "fire_safety"], "Skills array mismatch"
            print("PASS: VolunteerProfile defaults verified successfully.")

        # Test 2: Cross-society duplicate employee_id succeeds
        print("\n--- Test 2: Two SecurityProfiles in DIFFERENT societies with SAME employee_id (Must Succeed) ---")
        async with AsyncSessionLocal() as session:
            sec1 = SecurityProfile(
                user_id=u_sec1_id,
                society_id=soc1_id,
                employee_id="SEC-EMP-001",
                shift_start=time(6, 0),
                shift_end=time(14, 0),
            )
            sec2 = SecurityProfile(
                user_id=u_sec2_id,
                society_id=soc2_id,
                employee_id="SEC-EMP-001",  # Same employee_id in soc2
                shift_start=time(14, 0),
                shift_end=time(22, 0),
            )
            session.add_all([sec1, sec2])
            await session.commit()
            print("PASS: Successfully created SecurityProfiles with same employee_id across different societies.")

        # Test 3: Same-society duplicate employee_id fails
        print("\n--- Test 3: Two SecurityProfiles in SAME society with SAME employee_id (Must Fail) ---")
        async with AsyncSessionLocal() as session:
            try:
                sec3_duplicate = SecurityProfile(
                    user_id=u_sec3_id,
                    society_id=soc1_id,  # Same society as sec1
                    employee_id="SEC-EMP-001",  # Collision in soc1
                )
                session.add(sec3_duplicate)
                await session.commit()
                raise AssertionError("FAIL: Allowed duplicate employee_id in the same society!")
            except IntegrityError:
                print("PASS: Database correctly rejected duplicate employee_id in the same society (composite unique constraint enforced).")

        # Test 4: EmergencyContact verification_status defaults to unverified
        print("\n--- Test 4: EmergencyContact verification_status defaults to unverified ---")
        async with AsyncSessionLocal() as session:
            emg = EmergencyContact(
                resident_id=u_res_id,
                name="Dr. Sarah Connor",
                phone="+919888888881",
                contact_type=ContactTypeEnum.medical,
                # verification_status left unassigned to verify default
            )
            session.add(emg)
            await session.commit()

        async with AsyncSessionLocal() as session:
            fetched_emg = (await session.execute(select(EmergencyContact).where(EmergencyContact.resident_id == u_res_id))).scalar_one()
            print(f"Emergency Contact: name='{fetched_emg.name}', type={fetched_emg.contact_type.value}, status={fetched_emg.verification_status.value}")
            assert fetched_emg.verification_status == ContactVerificationStatusEnum.unverified, "Expected verification_status to default to 'unverified'"
            print("PASS: EmergencyContact default verification_status verified successfully.")

    finally:
        # Test 5: Cleanup & Cascade Verification
        print("\n--- Test 5: Cleaning up all test data ---")
        await clean_test_data()

        # Confirm clean DB
        async with AsyncSessionLocal() as session:
            rem_vol = (await session.execute(select(VolunteerProfile))).fetchall()
            rem_sec = (await session.execute(select(SecurityProfile))).fetchall()
            rem_emg = (await session.execute(select(EmergencyContact))).fetchall()
            rem_soc = (await session.execute(select(Society))).fetchall()
            rem_usr = (await session.execute(select(User))).fetchall()
            print(f"Remaining rows in DB: Vol={len(rem_vol)}, Sec={len(rem_sec)}, Emg={len(rem_emg)}, Soc={len(rem_soc)}, Usr={len(rem_usr)}")
            assert len(rem_vol) == 0 and len(rem_sec) == 0 and len(rem_emg) == 0 and len(rem_soc) == 0 and len(rem_usr) == 0
            print("Database completely cleaned. All tests passed!")


async def main():
    await verify_schema()
    await verify_models_behavior()
    await engine.dispose()
    print("\nALL VERIFICATION STEPS COMPLETED WITH 100% SUCCESS!")


if __name__ == "__main__":
    asyncio.run(main())
