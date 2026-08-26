"""End-to-end integration tests for OTP-Gated User Registration journeys."""

import asyncio
import pytest
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, RoleEnum
from app.models.otp_code import OtpCode, OtpPurposeEnum
from app.services.otp import OtpService
from tests.conftest import create_test_user


@pytest.mark.asyncio
async def test_registration_happy_path(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Request OTP -> Verify OTP -> Active user created without tokens."""
    phone = "+919811100001"
    email = "reg.happy@example.com"
    password = "StrongPassword123!"

    # 1. Request OTP
    req_res = await async_client.post(
        "/auth/register/request-otp",
        json={"phone": phone, "email": email},
    )
    assert req_res.status_code == 200
    req_json = req_res.json()
    assert "OTP has been sent" in req_json["message"]
    # Confirm code is NEVER returned in response
    assert "code" not in req_json

    # 2. Retrieve generated OTP code hash from DB and set a known code for verification
    otp_row = (
        await db_session.execute(
            select(OtpCode).where(
                OtpCode.phone == phone,
                OtpCode.purpose == OtpPurposeEnum.registration,
            )
        )
    ).scalar_one()
    assert otp_row.consumed_at is None
    assert len(otp_row.code_hash) == 64  # SHA-256 HMAC

    plain_code = "654321"
    otp_row.code_hash = OtpService.hash_otp_code(plain_code)
    await db_session.commit()

    # 3. Verify OTP and finalize registration
    verify_payload = {
        "phone": phone,
        "code": plain_code,
        "email": email,
        "password": password,
        "role": "resident",
    }
    verify_res = await async_client.post(
        "/auth/register/verify-otp",
        json=verify_payload,
    )
    assert verify_res.status_code == 201
    user_data = verify_res.json()
    assert user_data["email"] == email
    assert user_data["phone"] == phone
    assert user_data["role"] == "resident"
    assert user_data["is_active"] is True
    # Confirm security rules: hashed_password absent, tokens decoupled
    assert "hashed_password" not in user_data
    assert "password" not in user_data
    assert "access_token" not in user_data

    # 4. Verify DB state: User exists, OtpCode.consumed_at is set
    db_user = (await db_session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    assert db_user is not None

    await db_session.refresh(otp_row)
    assert otp_row.consumed_at is not None


@pytest.mark.asyncio
async def test_duplicate_registration_early_rejection(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Duplicate registration rejected with 409 before OTP dispatch."""
    existing_user = await create_test_user(
        db=db_session,
        email="existing.user@example.com",
        phone="+919811100002",
    )

    # 1. Attempt request-otp with duplicate phone
    dup_phone_res = await async_client.post(
        "/auth/register/request-otp",
        json={"phone": existing_user.phone, "email": "new.email@example.com"},
    )
    assert dup_phone_res.status_code == 409
    assert "phone" in dup_phone_res.json()["detail"].lower()

    # 2. Attempt request-otp with duplicate email
    dup_email_res = await async_client.post(
        "/auth/register/request-otp",
        json={"phone": "+919811100099", "email": existing_user.email},
    )
    assert dup_email_res.status_code == 409
    assert "email" in dup_email_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_expired_otp_rejection(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Expired OTP rejected with 400; no User created."""
    phone = "+919811100003"
    email = "expired.otp@example.com"

    # 1. Request OTP
    await async_client.post("/auth/register/request-otp", json={"phone": phone, "email": email})

    # 2. Force OTP record expiration directly in DB
    otp_row = (
        await db_session.execute(
            select(OtpCode).where(OtpCode.phone == phone)
        )
    ).scalar_one()
    otp_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    otp_row.code_hash = OtpService.hash_otp_code("123456")
    await db_session.commit()

    # 3. Attempt verification
    verify_res = await async_client.post(
        "/auth/register/verify-otp",
        json={
            "phone": phone,
            "code": "123456",
            "email": email,
            "password": "Password123!",
            "role": "resident",
        },
    )
    assert verify_res.status_code == 400
    assert "expired or not found" in verify_res.json()["detail"].lower()

    # Confirm no User was created
    user_count = (await db_session.execute(select(func.count(User.id)).where(User.email == email))).scalar()
    assert user_count == 0


@pytest.mark.asyncio
async def test_wrong_code_and_attempts_lockout(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Repeated wrong guesses lockout the code; correct code after lockout fails."""
    phone = "+919811100004"
    email = "lockout.test@example.com"
    correct_code = "777888"

    # 1. Request OTP
    await async_client.post("/auth/register/request-otp", json={"phone": phone, "email": email})

    # Set known hash
    otp_row = (await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
    otp_row.code_hash = OtpService.hash_otp_code(correct_code)
    await db_session.commit()

    # 2. Submit wrong code 5 times
    for i in range(1, 6):
        res = await async_client.post(
            "/auth/register/verify-otp",
            json={
                "phone": phone,
                "code": "000000",
                "email": email,
                "password": "Password123!",
                "role": "resident",
            },
        )
        assert res.status_code == 400
        assert "Invalid verification code" in res.json()["detail"]

    # 3. 6th attempt triggers lockout error
    lockout_res = await async_client.post(
        "/auth/register/verify-otp",
        json={
            "phone": phone,
            "code": "000000",
            "email": email,
            "password": "Password123!",
            "role": "resident",
        },
    )
    assert lockout_res.status_code == 400
    assert "Maximum verification attempts exceeded" in lockout_res.json()["detail"]

    # 4. Supplying the CORRECT code after lockout is still rejected (code is consumed/dead)
    post_lockout_res = await async_client.post(
        "/auth/register/verify-otp",
        json={
            "phone": phone,
            "code": correct_code,
            "email": email,
            "password": "Password123!",
            "role": "resident",
        },
    )
    assert post_lockout_res.status_code == 400
    assert "expired or not found" in post_lockout_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reused_consumed_otp_rejected(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Once an OTP is consumed, it cannot be reused."""
    phone = "+919811100005"
    email_a = "reuse.first@example.com"
    email_b = "reuse.second@example.com"
    code = "112233"

    # Request and configure OTP
    await async_client.post("/auth/register/request-otp", json={"phone": phone, "email": email_a})
    otp_row = (await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
    otp_row.code_hash = OtpService.hash_otp_code(code)
    await db_session.commit()

    # 1. First registration succeeds
    res_1 = await async_client.post(
        "/auth/register/verify-otp",
        json={
            "phone": phone,
            "code": code,
            "email": email_a,
            "password": "Password123!",
            "role": "resident",
        },
    )
    assert res_1.status_code == 201

    # 2. Attempt verify-otp again with same code for a different account
    res_2 = await async_client.post(
        "/auth/register/verify-otp",
        json={
            "phone": phone,
            "code": code,
            "email": email_b,
            "password": "Password123!",
            "role": "resident",
        },
    )
    assert res_2.status_code == 400
    assert "expired or not found" in res_2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_race_condition_double_registration(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Concurrent verify-otp calls result in exactly 1 created user."""
    phone = "+919811100006"
    email = "race.test@example.com"
    code = "998877"

    await async_client.post("/auth/register/request-otp", json={"phone": phone, "email": email})
    otp_row = (await db_session.execute(select(OtpCode).where(OtpCode.phone == phone))).scalar_one()
    otp_row.code_hash = OtpService.hash_otp_code(code)
    await db_session.commit()

    payload = {
        "phone": phone,
        "code": code,
        "email": email,
        "password": "Password123!",
        "role": "resident",
    }

    # Fire two concurrent calls
    results = await asyncio.gather(
        async_client.post("/auth/register/verify-otp", json=payload),
        async_client.post("/auth/register/verify-otp", json=payload),
        return_exceptions=True,
    )

    statuses = [r.status_code for r in results if isinstance(r, httpx.Response)]
    # Exactly one should succeed (201) and one should fail (400 or 409)
    assert 201 in statuses
    assert len([s for s in statuses if s == 201]) == 1

    # Verify exactly 1 user row in database
    users = (await db_session.execute(select(User).where(User.email == email))).scalars().all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_role_escalation_rejected_at_schema(
    async_client: httpx.AsyncClient,
):
    """User Journey: Public registration with admin/superadmin role is rejected with 422."""
    for forbidden_role in ["admin", "superadmin"]:
        res = await async_client.post(
            "/auth/register/verify-otp",
            json={
                "phone": "+919811100007",
                "code": "123456",
                "email": f"hacker.{forbidden_role}@example.com",
                "password": "Password123!",
                "role": forbidden_role,
            },
        )
        assert res.status_code == 422
