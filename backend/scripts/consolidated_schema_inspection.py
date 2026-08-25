"""Consolidated Schema Inspection connecting strictly as erp_app_user."""

import asyncio
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.db import engine


async def run_inspection():
    print("================================================================================")
    print("CONSOLIDATED SCHEMA VERIFICATION - PHASE 2 DOMAIN MODELS")
    print("================================================================================")

    async with engine.connect() as conn:
        # Check current user and database
        user_res = await conn.execute(text("SELECT current_user, current_database()"))
        current_user, current_db = user_res.fetchone()
        print(f"Connected User    : {current_user}")
        print(f"Connected Database: {current_db}")
        assert current_user == "erp_app_user", f"Expected erp_app_user, got {current_user}"
        assert current_db == "community_response_db", f"Expected community_response_db, got {current_db}"
        print("-> Application Role Connection: CONFIRMED\n")

        # Fetch all tables in public schema
        tbl_res = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            )
        )
        tables = [row[0] for row in tbl_res.fetchall()]
        print(f"All Public Tables ({len(tables)}): {tables}\n")

        expected_tables = [
            "users",
            "societies",
            "blocks",
            "flats",
            "resident_profiles",
            "guardian_links",
            "volunteer_profiles",
            "security_profiles",
            "emergency_contacts",
        ]
        for t in expected_tables:
            assert t in tables, f"Missing table: {t}"

        # ------------------------------------------------------------------------
        # 1. users
        # ------------------------------------------------------------------------
        print("--- 1. Table: users ---")
        col_res = await conn.execute(
            text(
                "SELECT column_name, data_type, udt_name, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position"
            )
        )
        users_cols = {r[0]: (r[1], r[2], r[3]) for r in col_res.fetchall()}
        print(f"  Columns: {list(users_cols.keys())}")
        print(f"  Role Column Type: data_type='{users_cols['role'][0]}', udt_name='{users_cols['role'][1]}'")
        assert users_cols['role'][0] == "USER-DEFINED" and users_cols['role'][1] == "role_enum"

        idx_res = await conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'users' ORDER BY indexname"
            )
        )
        users_idxs = idx_res.fetchall()
        idx_names = [i[0] for i in users_idxs]
        print(f"  Indexes: {idx_names}")
        assert "ix_users_email" in idx_names and "ix_users_phone" in idx_names
        print("  [PASS] users table structural check")

        # ------------------------------------------------------------------------
        # 2. societies
        # ------------------------------------------------------------------------
        print("\n--- 2. Table: societies ---")
        col_res = await conn.execute(
            text(
                "SELECT column_name, data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_name = 'societies' AND column_name IN ('latitude', 'longitude')"
            )
        )
        soc_cols = col_res.fetchall()
        for c in soc_cols:
            print(f"  {c[0]}: data_type='{c[1]}', precision={c[2]}, scale={c[3]}")
            assert c[1] == "numeric", f"Expected numeric, got {c[1]}"
            assert c[2] == 10 and c[3] == 7
        print("  [PASS] societies table structural check")

        # ------------------------------------------------------------------------
        # 3. blocks
        # ------------------------------------------------------------------------
        print("\n--- 3. Table: blocks ---")
        fk_res = await conn.execute(
            text(
                "SELECT tc.constraint_name, kcu.column_name, ccu.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'blocks'"
            )
        )
        blocks_fks = fk_res.fetchall()
        for fk in blocks_fks:
            print(f"  FK: {fk[1]} -> {fk[2]} (on_delete={fk[3]})")
            if fk[1] == "society_id":
                assert fk[3] == "CASCADE"
        print("  [PASS] blocks table structural check")

        # ------------------------------------------------------------------------
        # 4. flats
        # ------------------------------------------------------------------------
        print("\n--- 4. Table: flats ---")
        fk_res = await conn.execute(
            text(
                "SELECT kcu.column_name, ccu.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'flats'"
            )
        )
        flats_fks = fk_res.fetchall()
        for fk in flats_fks:
            print(f"  FK: {fk[0]} -> {fk[1]} (on_delete={fk[2]})")
            if fk[0] == "block_id":
                assert fk[2] == "CASCADE"

        uq_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "WHERE conrelid = 'flats'::regclass AND contype = 'u'"
            )
        )
        flats_uqs = uq_res.fetchall()
        uq_names = [u[0] for u in flats_uqs]
        print(f"  Unique Constraints: {flats_uqs}")
        assert "uq_block_unit_number" in uq_names
        print("  [PASS] flats table structural check")

        # ------------------------------------------------------------------------
        # 5. resident_profiles
        # ------------------------------------------------------------------------
        print("\n--- 5. Table: resident_profiles ---")
        uq_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "WHERE conrelid = 'resident_profiles'::regclass AND contype = 'u'"
            )
        )
        res_uqs = uq_res.fetchall()
        print(f"  Unique Constraints (1:1 guarantee): {res_uqs}")
        has_user_uq = any("user_id" in u[1] for u in res_uqs)
        assert has_user_uq, "Missing unique constraint on resident_profiles.user_id"

        fk_res = await conn.execute(
            text(
                "SELECT kcu.column_name, ccu.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'resident_profiles'"
            )
        )
        res_fks = fk_res.fetchall()
        for fk in res_fks:
            print(f"  FK: {fk[0]} -> {fk[1]} (on_delete={fk[2]})")
            if fk[0] == "user_id":
                assert fk[2] == "CASCADE"
            elif fk[0] == "flat_id":
                assert fk[2] == "SET NULL"
        print("  [PASS] resident_profiles table structural check")

        # ------------------------------------------------------------------------
        # 6. guardian_links
        # ------------------------------------------------------------------------
        print("\n--- 6. Table: guardian_links ---")
        fk_res = await conn.execute(
            text(
                "SELECT kcu.column_name, ccu.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'guardian_links'"
            )
        )
        g_fks = fk_res.fetchall()
        for fk in g_fks:
            print(f"  FK: {fk[0]} -> {fk[1]} (on_delete={fk[2]})")
            assert fk[1] == "users" and fk[2] == "CASCADE"

        chk_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "WHERE conrelid = 'guardian_links'::regclass AND contype = 'c'"
            )
        )
        g_chks = chk_res.fetchall()
        print(f"  Check Constraints: {g_chks}")
        assert any("guardian_id" in c[1] and "resident_id" in c[1] for c in g_chks)

        uq_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "WHERE conrelid = 'guardian_links'::regclass AND contype = 'u'"
            )
        )
        g_uqs = uq_res.fetchall()
        print(f"  Composite Unique Constraints: {g_uqs}")
        assert any("guardian_id" in u[1] and "resident_id" in u[1] for u in g_uqs)

        idx_res = await conn.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'guardian_links' AND indexname = 'uq_one_primary_guardian_per_resident'"
            )
        )
        partial_idx = idx_res.fetchone()
        print(f"  Partial Unique Index: {partial_idx[0]} -> {partial_idx[1]}")
        assert "WHERE (priority = 'primary'::guardian_priority_enum)" in partial_idx[1] or "WHERE priority = 'primary'" in partial_idx[1]
        print("  [PASS] guardian_links table structural check")

        # ------------------------------------------------------------------------
        # 7. volunteer_profiles
        # ------------------------------------------------------------------------
        print("\n--- 7. Table: volunteer_profiles ---")
        col_res = await conn.execute(
            text(
                "SELECT column_name, data_type, udt_name, column_default "
                "FROM information_schema.columns WHERE table_name = 'volunteer_profiles' AND column_name IN ('skills', 'availability_status')"
            )
        )
        vol_cols = {r[0]: (r[1], r[2], r[3]) for r in col_res.fetchall()}
        print(f"  skills: data_type='{vol_cols['skills'][0]}', udt_name='{vol_cols['skills'][1]}'")
        print(f"  availability_status: udt_name='{vol_cols['availability_status'][1]}', default='{vol_cols['availability_status'][2]}'")
        assert vol_cols['skills'][0] == "ARRAY" and vol_cols['skills'][1] == "_varchar"
        assert "off_duty" in vol_cols['availability_status'][2]

        uq_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "WHERE conrelid = 'volunteer_profiles'::regclass AND contype = 'u'"
            )
        )
        vol_uqs = uq_res.fetchall()
        print(f"  Unique Constraints (1:1 guarantee): {vol_uqs}")
        assert any("user_id" in u[1] for u in vol_uqs)
        print("  [PASS] volunteer_profiles table structural check")

        # ------------------------------------------------------------------------
        # 8. security_profiles
        # ------------------------------------------------------------------------
        print("\n--- 8. Table: security_profiles ---")
        uq_res = await conn.execute(
            text(
                "SELECT conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "WHERE conrelid = 'security_profiles'::regclass AND contype = 'u'"
            )
        )
        sec_uqs = uq_res.fetchall()
        print(f"  Unique Constraints: {sec_uqs}")
        assert any("society_id" in u[1] and "employee_id" in u[1] for u in sec_uqs)

        fk_res = await conn.execute(
            text(
                "SELECT kcu.column_name, ccu.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'security_profiles'"
            )
        )
        sec_fks = fk_res.fetchall()
        for fk in sec_fks:
            print(f"  FK: {fk[0]} -> {fk[1]} (on_delete={fk[2]})")
            if fk[0] == "assigned_block_id":
                assert fk[2] == "SET NULL"
        print("  [PASS] security_profiles table structural check")

        # ------------------------------------------------------------------------
        # 9. emergency_contacts
        # ------------------------------------------------------------------------
        print("\n--- 9. Table: emergency_contacts ---")
        enum_res = await conn.execute(
            text(
                "SELECT e.enumlabel FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid "
                "WHERE t.typname = 'contact_verification_status_enum' ORDER BY e.enumsortorder"
            )
        )
        enum_vals = [r[0] for r in enum_res.fetchall()]
        print(f"  verification_status enum labels: {enum_vals}")
        assert enum_vals == ["unverified", "pending", "verified"]

        col_res = await conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = 'emergency_contacts' AND column_name = 'last_verified_at'"
            )
        )
        col = col_res.fetchone()
        print(f"  last_verified_at: data_type='{col[1]}', is_nullable='{col[2]}'")
        assert col[1] == "timestamp with time zone" and col[2] == "YES"
        print("  [PASS] emergency_contacts table structural check")

    print("\n================================================================================")
    print("ALL CONSOLIDATED SCHEMA CHECKS PASSED WITH 100% SUCCESS!")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(run_inspection())
