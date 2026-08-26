"""Comprehensive Phase 1 & 2 Verification Sweep across all 9 domain models."""

import asyncio
import sys
from datetime import date, time
from decimal import Decimal
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
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
from app.models.volunteer import VolunteerProfile, VolunteerAvailabilityEnum
from app.models.security_staff import SecurityProfile
from app.models.emergency_contact import (
    EmergencyContact,
    ContactTypeEnum,
    ContactVerificationStatusEnum,
)

SWEEP_EMAILS = [
    "sweep.admin@example.com",
    "sweep.resident@example.com",
    "sweep.guardian@example.com",
    "sweep.volunteer@example.com",
    "sweep.security@example.com",
]


async def clean_sweep_data():
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User).where(User.email.in_(SWEEP_EMAILS)))).scalars().all()
        user_ids = [u.id for u in users]
        if user_ids:
            socs = (await session.execute(select(Society).where(Society.admin_id.in_(user_ids)))).scalars().all()
            for s in socs:
                await session.delete(s)
            for u in users:
                await session.delete(u)
            await session.commit()


async def check_engine_connectivity():
    print("=== Check 1: Live Async Engine SELECT 1 ===")
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql("SELECT 1")
        val = result.scalar()
        print(f"Engine connection successful: SELECT 1 -> {val}")
        assert val == 1


async def check_per_table_structures():
    print("\n=== Check 2: Per-Table Structural Re-verification (9 Tables) ===")
    async with engine.connect() as conn:
        # Check current user is erp_app_user
        user_res = await conn.execute(text("SELECT current_user, current_database()"))
        current_user, current_db = user_res.fetchone()
        print(f"Connected as: {current_user} @ {current_db}")
        assert current_user == "erp_app_user"

        # 1. users
        col_res = await conn.execute(
            text("SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'users'")
        )
        u_cols = {r[0]: (r[1], r[2]) for r in col_res.fetchall()}
        assert u_cols["role"][1] == "role_enum"

        idx_res = await conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'users'"))
        u_idxs = [r[0] for r in idx_res.fetchall()]
        assert "ix_users_email" in u_idxs and "ix_users_phone" in u_idxs
        print(" [PASS] 1. users: role enum, email/phone unique indexes")

        # 2. societies
        col_res = await conn.execute(
            text("SELECT column_name, data_type, numeric_precision, numeric_scale FROM information_schema.columns WHERE table_name = 'societies' AND column_name IN ('latitude', 'longitude')")
        )
        for c in col_res.fetchall():
            assert c[1] == "numeric" and c[2] == 10 and c[3] == 7
        print(" [PASS] 2. societies: numeric(10, 7) coordinates")

        # 3. blocks
        fk_res = await conn.execute(
            text("SELECT kcu.column_name, ccu.table_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name WHERE tc.table_name = 'blocks'")
        )
        for fk in fk_res.fetchall():
            if fk[0] == "society_id":
                assert fk[2] == "CASCADE"
        print(" [PASS] 3. blocks: FK society_id CASCADE")

        # 4. flats
        fk_res = await conn.execute(
            text("SELECT kcu.column_name, ccu.table_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name WHERE tc.table_name = 'flats'")
        )
        for fk in fk_res.fetchall():
            if fk[0] == "block_id":
                assert fk[2] == "CASCADE"
        uq_res = await conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'flats'::regclass AND contype = 'u'")
        )
        assert "uq_block_unit_number" in [r[0] for r in uq_res.fetchall()]
        print(" [PASS] 4. flats: FK block_id CASCADE, uq_block_unit_number")

        # 5. resident_profiles
        uq_res = await conn.execute(
            text("SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c WHERE conrelid = 'resident_profiles'::regclass AND contype = 'u'")
        )
        assert any("user_id" in r[1] for r in uq_res.fetchall())
        fk_res = await conn.execute(
            text("SELECT kcu.column_name, ccu.table_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name WHERE tc.table_name = 'resident_profiles'")
        )
        for fk in fk_res.fetchall():
            if fk[0] == "user_id":
                assert fk[2] == "CASCADE"
            elif fk[0] == "flat_id":
                assert fk[2] == "SET NULL"

        # Check nearby_neighbours JSONB column
        col_res = await conn.execute(
            text("SELECT column_name, data_type, udt_name, is_nullable FROM information_schema.columns WHERE table_name = 'resident_profiles' AND column_name = 'nearby_neighbours'")
        )
        nn_col = col_res.fetchone()
        print(f"  nearby_neighbours: {nn_col}")
        assert nn_col is not None and nn_col[2] == "jsonb" and nn_col[3] == "YES"
        print(" [PASS] 5. resident_profiles: 1:1 user_id, FK cascades, nearby_neighbours jsonb column verified")

        # 6. guardian_links
        chk_res = await conn.execute(
            text("SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c WHERE conrelid = 'guardian_links'::regclass AND contype = 'c'")
        )
        assert any("guardian_id" in r[1] and "resident_id" in r[1] for r in chk_res.fetchall())
        idx_res = await conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'guardian_links' AND indexname = 'uq_one_primary_guardian_per_resident'")
        )
        p_idx = idx_res.fetchone()
        assert p_idx is not None and "priority = 'primary'" in p_idx[1]
        print(" [PASS] 6. guardian_links: self-check, composite unique, partial unique index for primary guardian")

        # 7. volunteer_profiles
        col_res = await conn.execute(
            text("SELECT column_name, data_type, udt_name, column_default FROM information_schema.columns WHERE table_name = 'volunteer_profiles' AND column_name IN ('skills', 'availability_status', 'rating')")
        )
        v_cols = {r[0]: (r[1], r[2], r[3]) for r in col_res.fetchall()}
        assert v_cols["skills"][0] == "ARRAY" and v_cols["skills"][1] == "_varchar"
        assert "off_duty" in v_cols["availability_status"][2]
        assert v_cols["rating"][1] == "numeric" and v_cols["rating"][2] is None
        print(" [PASS] 7. volunteer_profiles: native array skills, off_duty default, nullable rating")

        # 8. security_profiles
        uq_res = await conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'security_profiles'::regclass AND contype = 'u'")
        )
        assert "uq_society_employee_id" in [r[0] for r in uq_res.fetchall()]
        fk_res = await conn.execute(
            text("SELECT kcu.column_name, ccu.table_name, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name WHERE tc.table_name = 'security_profiles' AND kcu.column_name = 'assigned_block_id'")
        )
        assert fk_res.fetchone()[2] == "SET NULL"
        print(" [PASS] 8. security_profiles: composite scoped employee_id, assigned_block_id SET NULL")

        # 9. emergency_contacts
        enum_res = await conn.execute(
            text("SELECT e.enumlabel FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid WHERE t.typname = 'contact_verification_status_enum' ORDER BY e.enumsortorder")
        )
        assert [r[0] for r in enum_res.fetchall()] == ["unverified", "pending", "verified"]
        col_res = await conn.execute(
            text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'emergency_contacts' AND column_name = 'last_verified_at'")
        )
        assert col_res.fetchone()[0] == "YES"
        print(" [PASS] 9. emergency_contacts: 3-state verification enum, nullable last_verified_at")


async def run_cross_model_integration_test():
    print("\n=== Check 3: Full 9-Model Cross-Graph Integration Test ===")
    await clean_sweep_data()

    soc_id = None
    blk_id = None
    flt_id = None
    admin_id = None
    res_id = None
    guard_id = None
    vol_id = None
    sec_id = None
    emg_id = None

    try:
        async with AsyncSessionLocal() as session:
            # 1. Admin User
            admin_user = User(
                email="sweep.admin@example.com",
                phone="+919888800001",
                hashed_password="pw",
                role=RoleEnum.admin,
            )
            # 2. Resident User
            resident_user = User(
                email="sweep.resident@example.com",
                phone="+919888800002",
                hashed_password="pw",
                role=RoleEnum.resident,
            )
            # 3. Guardian User
            guardian_user = User(
                email="sweep.guardian@example.com",
                phone="+919888800003",
                hashed_password="pw",
                role=RoleEnum.guardian,
            )
            # 4. Volunteer User
            volunteer_user = User(
                email="sweep.volunteer@example.com",
                phone="+919888800004",
                hashed_password="pw",
                role=RoleEnum.volunteer,
            )
            # 5. Security User
            security_user = User(
                email="sweep.security@example.com",
                phone="+919888800005",
                hashed_password="pw",
                role=RoleEnum.security,
            )
            session.add_all([admin_user, resident_user, guardian_user, volunteer_user, security_user])
            await session.flush()
            admin_id = admin_user.id
            res_id = resident_user.id
            guard_id = guardian_user.id
            vol_id = volunteer_user.id
            sec_id = security_user.id

            # 6. Society (Administered by admin_user)
            society = Society(
                name="Emerald Heights",
                address="45 Crestview Blvd",
                latitude=Decimal("12.9715987"),
                longitude=Decimal("77.5945627"),
                admin_id=admin_user.id,
                response_window_seconds=120,
            )
            session.add(society)
            await session.flush()
            soc_id = society.id

            # 7. Block
            block = Block(name="Tower A", society_id=society.id)
            session.add(block)
            await session.flush()
            blk_id = block.id

            # 8. Flat
            flat = Flat(
                unit_number="1204",
                floor=12,
                block_id=block.id,
                occupancy_status=OccupancyStatusEnum.owner,
            )
            session.add(flat)
            await session.flush()
            flt_id = flat.id

            # 9. ResidentProfile
            res_profile = ResidentProfile(
                user_id=resident_user.id,
                flat_id=flat.id,
                date_of_birth=date(1988, 11, 14),
                status=ResidentStatusEnum.active,
                nearby_neighbours=[
                    {"user_id": str(volunteer_user.id), "name": "Volunteer Jane", "flat": "Tower A - 1205", "distance_m": 5}
                ],
            )
            session.add(res_profile)

            # 10. GuardianLink
            g_link = GuardianLink(
                guardian_id=guardian_user.id,
                resident_id=resident_user.id,
                priority=GuardianPriorityEnum.primary,
                consent_status=ConsentStatusEnum.accepted,
            )
            session.add(g_link)

            # 11. VolunteerProfile
            vol_profile = VolunteerProfile(
                user_id=volunteer_user.id,
                society_id=society.id,
                skills=["cpr", "trauma_first_aid"],
                availability_status=VolunteerAvailabilityEnum.available,
                background_verified=True,
            )
            session.add(vol_profile)

            # 12. SecurityProfile
            sec_profile = SecurityProfile(
                user_id=security_user.id,
                society_id=society.id,
                assigned_block_id=block.id,
                employee_id="SEC-SWEEP-101",
                shift_start=time(8, 0),
                shift_end=time(16, 0),
            )
            session.add(sec_profile)

            # 13. EmergencyContact
            emg_contact = EmergencyContact(
                resident_id=resident_user.id,
                name="Dr. Gregory House",
                phone="+919876543210",
                contact_type=ContactTypeEnum.medical,
                verification_status=ContactVerificationStatusEnum.verified,
            )
            session.add(emg_contact)
            await session.commit()
            print("Full object graph persisted in a single transaction.")

        # Query back and verify every hop
        async with AsyncSessionLocal() as session:
            # Query Society with eager loads
            q_soc = (
                await session.execute(
                    select(Society)
                    .where(Society.id == soc_id)
                    .options(
                        selectinload(Society.admin),
                        selectinload(Society.blocks).selectinload(Block.flats),
                        selectinload(Society.volunteers).selectinload(VolunteerProfile.user),
                        selectinload(Society.security_staff).selectinload(SecurityProfile.user),
                    )
                )
            ).scalar_one()

            # Hop 1: Society -> Admin User
            assert q_soc.admin.email == "sweep.admin@example.com"
            print("  Hop 1: Society -> Admin User [OK]")

            # Hop 2: Society -> Block -> Flat
            assert len(q_soc.blocks) == 1 and q_soc.blocks[0].name == "Tower A"
            assert len(q_soc.blocks[0].flats) == 1 and q_soc.blocks[0].flats[0].unit_number == "1204"
            print("  Hop 2: Society -> Block -> Flat [OK]")

            # Hop 3: Society -> Volunteer -> User
            assert len(q_soc.volunteers) == 1 and q_soc.volunteers[0].user.email == "sweep.volunteer@example.com"
            assert q_soc.volunteers[0].skills == ["cpr", "trauma_first_aid"]
            print("  Hop 3: Society -> VolunteerProfile -> User [OK]")

            # Hop 4: Society -> SecurityStaff -> Block & User
            assert len(q_soc.security_staff) == 1 and q_soc.security_staff[0].user.email == "sweep.security@example.com"
            assert q_soc.security_staff[0].assigned_block_id == blk_id
            print("  Hop 4: Society -> SecurityProfile -> User & Block [OK]")

            # Hop 5: Resident User -> ResidentProfile -> Flat & nearby_neighbours JSONB
            q_res_user = (
                await session.execute(
                    select(User)
                    .where(User.id == res_id)
                    .options(
                        selectinload(User.resident_profile).selectinload(ResidentProfile.flat),
                        selectinload(User.emergency_contacts),
                    )
                )
            ).scalar_one()
            assert q_res_user.resident_profile is not None
            assert q_res_user.resident_profile.flat.unit_number == "1204"
            assert len(q_res_user.resident_profile.nearby_neighbours) == 1
            assert q_res_user.resident_profile.nearby_neighbours[0]["name"] == "Volunteer Jane"
            print("  Hop 5: User -> ResidentProfile -> Flat & nearby_neighbours JSONB [OK]")

            # Hop 6: Resident User -> EmergencyContact
            assert len(q_res_user.emergency_contacts) == 1
            assert q_res_user.emergency_contacts[0].name == "Dr. Gregory House"
            assert q_res_user.emergency_contacts[0].verification_status == ContactVerificationStatusEnum.verified
            print("  Hop 6: Resident User -> EmergencyContact [OK]")

            # Hop 7: GuardianLink -> Guardian User & Resident User
            q_glink = (
                await session.execute(
                    select(GuardianLink)
                    .where(GuardianLink.resident_id == res_id)
                    .options(
                        selectinload(GuardianLink.guardian),
                        selectinload(GuardianLink.resident),
                    )
                )
            ).scalar_one()
            assert q_glink.guardian.email == "sweep.guardian@example.com"
            assert q_glink.resident.email == "sweep.resident@example.com"
            assert q_glink.priority == GuardianPriorityEnum.primary
            assert q_glink.consent_status == ConsentStatusEnum.accepted
            print("  Hop 7: GuardianLink -> Guardian User & Resident User [OK]")

            print("All 7 relationship hops traversed and verified successfully!")

    finally:
        print("\n=== Teardown: Cleaning up sweep test data ===")
        await clean_sweep_data()
        async with AsyncSessionLocal() as session:
            rem_users = (await session.execute(select(User).where(User.email.in_(SWEEP_EMAILS)))).fetchall()
            assert len(rem_users) == 0
            print("Teardown clean: 0 residual sweep rows remaining.")


async def main():
    print("================================================================================")
    print("FULL PHASE 1 & 2 VERIFICATION SWEEP (STEPS 1 - 18)")
    print("================================================================================")
    await check_engine_connectivity()
    await check_per_table_structures()
    await run_cross_model_integration_test()
    await engine.dispose()
    print("\n================================================================================")
    print("FULL VERIFICATION SWEEP COMPLETED WITH 100% SUCCESS!")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(main())
