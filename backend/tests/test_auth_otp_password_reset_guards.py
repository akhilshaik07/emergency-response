"""Comprehensive integration tests for OTP Registration, Token Refresh, Password Reset, and Permission Guards."""

import pytest
import httpx
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password, create_access_token, create_refresh_token
from app.models.user import User, RoleEnum
from app.models.society import Society
from app.models.otp_code import OtpCode, OtpPurposeEnum
from app.services.otp import OtpService
from app.api.deps import get_current_user, require_role, require_society_scope

BASE_URL = "http://testserver"

# Dedicated dummy router to test require_role dependency factory
dummy_guard_router = APIRouter(prefix="/test-guards", tags=["TestGuards"])


@dummy_guard_router.get("/admin-only")
async def admin_only_endpoint(
    current_user: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
):
    return {"message": f"Welcome admin {current_user.email}"}


app.include_router(dummy_guard_router)


TEST_EMAILS = [
    "otp.resident@example.com",
    "otp.admin_a@example.com",
    "otp.admin_b@example.com",
    "otp.superadmin@example.com",
]

TEST_PHONES = [
    "+919876500001",
    "+919876500002",
    "+919876500003",
    "+919876500004",
]

test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


async def clean_test_data():
    async with TestSessionLocal() as session:
        # Clean OTP codes
        otps = (await session.execute(select(OtpCode).where(OtpCode.phone.in_(TEST_PHONES)))).scalars().all()
        for o in otps:
            await session.delete(o)

        # Clean users and their societies
        users = (await session.execute(select(User).where(User.email.in_(TEST_EMAILS)))).scalars().all()
        user_ids = [u.id for u in users]
        if user_ids:
            socs = (await session.execute(select(Society).where(Society.admin_id.in_(user_ids)))).scalars().all()
            for s in socs:
                await session.delete(s)
            for u in users:
                await session.delete(u)
        await session.commit()


@pytest.mark.asyncio
async def test_otp_gated_registration_full_flow_and_guards():
    await clean_test_data()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            phone = "+919876500001"
            email = "otp.resident@example.com"
            password = "SecurePassword123!"

            # 1. Request OTP
            req_res = await client.post(
                "/auth/register/request-otp",
                json={"phone": phone, "email": email},
            )
            assert req_res.status_code == 200
            assert "OTP has been sent" in req_res.json()["message"]

            # 2. Rate limit test: immediate repeated request returns 429
            rate_res = await client.post(
                "/auth/register/request-otp",
                json={"phone": phone, "email": email},
            )
            assert rate_res.status_code == 429
            assert "60 seconds" in rate_res.json()["detail"]

            # 3. Inspect generated OTP in database (retrieve hashed code)
            async with TestSessionLocal() as session:
                otp_row = (
                    await session.execute(
                        select(OtpCode).where(
                            and_(OtpCode.phone == phone, OtpCode.purpose == OtpPurposeEnum.registration)
                        )
                    )
                ).scalar_one()
                assert otp_row is not None
                assert otp_row.consumed_at is None
                assert len(otp_row.code_hash) == 64  # SHA256 hex string

                # For testing verify-otp, generate matching plain code & overwrite hash
                plain_code = "123456"
                otp_row.code_hash = OtpService.hash_otp_code(plain_code)
                await session.commit()

            # 4. Wrong code test: fails with 400 and increments attempts
            wrong_res = await client.post(
                "/auth/register/verify-otp",
                json={
                    "phone": phone,
                    "code": "999999",
                    "email": email,
                    "password": password,
                    "role": "resident",
                },
            )
            assert wrong_res.status_code == 400
            assert "Invalid verification code" in wrong_res.json()["detail"]

            async with TestSessionLocal() as session:
                otp_check = (await session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
                assert otp_check.attempts == 1

            # 5. Correct code verification -> 201 Created (User created, no tokens auto-issued)
            verify_res = await client.post(
                "/auth/register/verify-otp",
                json={
                    "phone": phone,
                    "code": "123456",
                    "email": email,
                    "password": password,
                    "role": "resident",
                },
            )
            assert verify_res.status_code == 201
            user_data = verify_res.json()
            assert user_data["email"] == email
            assert user_data["phone"] == phone
            assert "access_token" not in user_data  # Tokens separate

            # 6. Replay attack rejection: Calling verify-otp again fails because code is consumed
            replay_res = await client.post(
                "/auth/register/verify-otp",
                json={
                    "phone": phone,
                    "code": "123456",
                    "email": email,
                    "password": password,
                    "role": "resident",
                },
            )
            assert replay_res.status_code == 400
            assert "expired or not found" in replay_res.json()["detail"].lower()
    finally:
        await clean_test_data()


@pytest.mark.asyncio
async def test_token_refresh_and_role_re_resolution():
    await clean_test_data()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            # Create user in DB
            email = "otp.resident@example.com"
            phone = "+919876500001"
            async with TestSessionLocal() as session:
                user = User(
                    email=email,
                    phone=phone,
                    hashed_password=hash_password("Password123!"),
                    role=RoleEnum.resident,
                    is_active=True,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                user_id = user.id

            # Login
            login_res = await client.post(
                "/auth/login",
                json={"email": email, "password": "Password123!"},
            )
            assert login_res.status_code == 200
            tokens = login_res.json()
            initial_access = tokens["access_token"]
            refresh_tok = tokens["refresh_token"]

            # Refresh token exchange -> 200 OK with new tokens
            ref_res = await client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_tok},
            )
            assert ref_res.status_code == 200
            ref_data = ref_res.json()
            assert "access_token" in ref_data
            assert "refresh_token" in ref_data

            # Test refresh rejection for deactivated user
            async with TestSessionLocal() as session:
                db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
                db_user.is_active = False
                await session.commit()

            ref_deact = await client.post(
                "/auth/refresh",
                json={"refresh_token": ref_data["refresh_token"]},
            )
            assert ref_deact.status_code == 401
    finally:
        await clean_test_data()


@pytest.mark.asyncio
async def test_password_reset_flow_anti_enumeration_and_reset():
    await clean_test_data()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            email = "otp.resident@example.com"
            phone = "+919876500001"
            old_password = "OldPassword123!"
            new_password = "NewSuperSecret456!"

            # Create active user
            async with TestSessionLocal() as session:
                user = User(
                    email=email,
                    phone=phone,
                    hashed_password=hash_password(old_password),
                    role=RoleEnum.resident,
                    is_active=True,
                )
                session.add(user)
                await session.commit()

            # 1. Request OTP for existing account
            req_real = await client.post(
                "/auth/password-reset/request-otp",
                json={"identifier": email},
            )
            assert req_real.status_code == 200
            real_body = req_real.json()

            # 2. Request OTP for non-existent account -> MUST return IDENTICAL body
            req_fake = await client.post(
                "/auth/password-reset/request-otp",
                json={"identifier": "nonexistent@example.com"},
            )
            assert req_fake.status_code == 200
            fake_body = req_fake.json()
            assert real_body == fake_body
            assert real_body["message"] == "If an account exists with this identifier, an OTP has been sent."

            # 3. Retrieve and set known OTP in DB for testing reset
            async with TestSessionLocal() as session:
                otp_row = (
                    await session.execute(
                        select(OtpCode).where(
                            and_(OtpCode.phone == phone, OtpCode.purpose == OtpPurposeEnum.password_reset)
                        )
                    )
                ).scalar_one()
                otp_row.code_hash = OtpService.hash_otp_code("654321")
                await session.commit()

            # 4. Verify and reset password
            reset_res = await client.post(
                "/auth/password-reset/verify-and-reset",
                json={
                    "identifier": email,
                    "code": "654321",
                    "new_password": new_password,
                },
            )
            assert reset_res.status_code == 200
            assert "Password has been reset successfully" in reset_res.json()["message"]

            # 5. Confirm old password fails to log in
            login_old = await client.post(
                "/auth/login",
                json={"email": email, "password": old_password},
            )
            assert login_old.status_code == 401

            # 6. Confirm new password logs in successfully
            login_new = await client.post(
                "/auth/login",
                json={"email": email, "password": new_password},
            )
            assert login_new.status_code == 200
            assert "access_token" in login_new.json()
    finally:
        await clean_test_data()


@pytest.mark.asyncio
async def test_role_and_society_permission_guards():
    await clean_test_data()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            # Create users: Resident, Admin A, Admin B, Superadmin
            async with TestSessionLocal() as session:
                res_user = User(email="otp.resident@example.com", phone="+919876500001", hashed_password=hash_password("Pass123!"), role=RoleEnum.resident, is_active=True)
                admin_a = User(email="otp.admin_a@example.com", phone="+919876500002", hashed_password=hash_password("Pass123!"), role=RoleEnum.admin, is_active=True)
                admin_b = User(email="otp.admin_b@example.com", phone="+919876500003", hashed_password=hash_password("Pass123!"), role=RoleEnum.admin, is_active=True)
                super_user = User(email="otp.superadmin@example.com", phone="+919876500004", hashed_password=hash_password("Pass123!"), role=RoleEnum.superadmin, is_active=True)
                session.add_all([res_user, admin_a, admin_b, super_user])
                await session.commit()
                await session.refresh(res_user)
                await session.refresh(admin_a)
                await session.refresh(admin_b)
                await session.refresh(super_user)

                res_id = res_user.id
                admin_a_id = admin_a.id
                admin_b_id = admin_b.id
                super_id = super_user.id

                # Create Society owned by Admin A
                soc_a = Society(
                    name="Emerald Haven",
                    address="100 Green Avenue",
                    latitude=Decimal("12.9716"),
                    longitude=Decimal("77.5946"),
                    admin_id=admin_a_id,
                    response_window_seconds=120,
                )
                session.add(soc_a)
                await session.commit()
                await session.refresh(soc_a)
                soc_a_id = soc_a.id

            token_res = create_access_token(str(res_id), role=RoleEnum.resident.value)
            token_admin_a = create_access_token(str(admin_a_id), role=RoleEnum.admin.value)
            token_admin_b = create_access_token(str(admin_b_id), role=RoleEnum.admin.value)
            token_super = create_access_token(str(super_id), role=RoleEnum.superadmin.value)

            # 1. require_role guard tests
            # Resident -> 403 Forbidden
            r_res = await client.get("/test-guards/admin-only", headers={"Authorization": f"Bearer {token_res}"})
            assert r_res.status_code == 403

            # Admin A -> 200 OK
            r_admin = await client.get("/test-guards/admin-only", headers={"Authorization": f"Bearer {token_admin_a}"})
            assert r_admin.status_code == 200

            # Superadmin -> 200 OK
            r_super = await client.get("/test-guards/admin-only", headers={"Authorization": f"Bearer {token_super}"})
            assert r_super.status_code == 200

            # 2. require_society_scope tests on PATCH /societies/{id}
            # Admin A (Owner) -> 200 OK
            patch_owner = await client.patch(
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_admin_a}"},
                json={"name": "Emerald Haven Heights"},
            )
            assert patch_owner.status_code == 200
            assert patch_owner.json()["name"] == "Emerald Haven Heights"

            # Admin B (Different Society Admin) -> 403 Forbidden
            patch_other_admin = await client.patch(
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_admin_b}"},
                json={"name": "Hacked Name"},
            )
            assert patch_other_admin.status_code == 403

            # Resident -> 403 Forbidden
            patch_resident = await client.patch(
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_res}"},
                json={"name": "Resident Name"},
            )
            assert patch_resident.status_code == 403

            # Superadmin -> 200 OK (Platform-wide override)
            patch_super = await client.patch(
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_super}"},
                json={"response_window_seconds": 180},
            )
            assert patch_super.status_code == 200
            assert patch_super.json()["response_window_seconds"] == 180

            # Non-existent society -> 404 Not Found
            import uuid
            fake_soc_id = uuid.uuid4()
            patch_404 = await client.patch(
                f"/societies/{fake_soc_id}",
                headers={"Authorization": f"Bearer {token_admin_a}"},
                json={"name": "Ghost Society"},
            )
            assert patch_404.status_code == 404

            # 3. require_society_scope tests on DELETE /societies/{id}
            # Resident -> 403 Forbidden
            del_resident = await client.request(
                "DELETE",
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_res}"},
                json={"confirmation_name": "Emerald Haven Heights"},
            )
            assert del_resident.status_code == 403

            # Admin B -> 403 Forbidden
            del_other_admin = await client.request(
                "DELETE",
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_admin_b}"},
                json={"confirmation_name": "Emerald Haven Heights"},
            )
            assert del_other_admin.status_code == 403

            # Admin A with wrong confirmation name -> 400 Bad Request
            del_mismatch = await client.request(
                "DELETE",
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_admin_a}"},
                json={"confirmation_name": "Wrong Name"},
            )
            assert del_mismatch.status_code == 400

            # Admin A with valid confirmation name -> 200 OK
            del_success = await client.request(
                "DELETE",
                f"/societies/{soc_a_id}",
                headers={"Authorization": f"Bearer {token_admin_a}"},
                json={"confirmation_name": "Emerald Haven Heights"},
            )
            assert del_success.status_code == 200
            assert "deleted" in del_success.json()["message"].lower()
    finally:
        await clean_test_data()
