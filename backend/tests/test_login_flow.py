"""End-to-end integration tests for Authentication, Credential Security, and Token Refresh."""

import pytest
import httpx
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, create_refresh_token
from app.models.user import RoleEnum
from tests.conftest import create_test_user


@pytest.mark.asyncio
async def test_login_happy_path_and_claims(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Login with credentials -> Receive valid JWT access & refresh tokens with verified claims."""
    user = await create_test_user(
        db=db_session,
        role=RoleEnum.resident,
        password="ValidPassword123!",
    )

    # 1. Login via email
    res = await async_client.post(
        "/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # 2. Decode access token using app's decode_token and verify claims
    payload = decode_token(data["access_token"])
    assert payload["sub"] == str(user.id)
    assert payload["role"] == RoleEnum.resident.value
    assert payload["type"] == "access"
    assert "exp" in payload

    # 3. Decode refresh token
    ref_payload = decode_token(data["refresh_token"])
    assert ref_payload["sub"] == str(user.id)
    assert ref_payload["type"] == "refresh"
    assert "role" not in ref_payload  # Refresh tokens carry minimal claims


@pytest.mark.asyncio
async def test_wrong_password_and_nonexistent_identifier_enumeration_defense(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Security Invariant: Wrong password, non-existent email, and non-existent phone produce IDENTICAL responses."""
    user = await create_test_user(
        db=db_session,
        password="RealPassword123!",
    )

    # 1. Real account + wrong password
    wrong_pwd_res = await async_client.post(
        "/auth/login",
        json={"email": user.email, "password": "WrongPassword456!"},
    )
    assert wrong_pwd_res.status_code == 401

    # 2. Non-existent email
    fake_email_res = await async_client.post(
        "/auth/login",
        json={"email": "nonexistent.account@example.com", "password": "AnyPassword123!"},
    )
    assert fake_email_res.status_code == 401

    # 3. Non-existent phone
    fake_phone_res = await async_client.post(
        "/auth/login",
        json={"phone": "+919900099999", "password": "AnyPassword123!"},
    )
    assert fake_phone_res.status_code == 401

    # Assert exact equality of response bodies across all cases (account enumeration defense)
    assert wrong_pwd_res.json() == fake_email_res.json()
    assert wrong_pwd_res.json() == fake_phone_res.json()
    assert wrong_pwd_res.json()["detail"] == "Incorrect email/phone or password."


@pytest.mark.asyncio
async def test_soft_deleted_account_login_enumeration_defense(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Security Invariant: Soft-deleted (deactivated) account produces the SAME error as non-existent user."""
    user = await create_test_user(
        db=db_session,
        password="MyPassword123!",
        is_active=False,  # Soft deleted
    )

    res = await async_client.post(
        "/auth/login",
        json={"email": user.email, "password": "MyPassword123!"},
    )
    assert res.status_code == 401
    # MUST NOT leak "Account is deactivated"
    assert res.json()["detail"] == "Incorrect email/phone or password."


@pytest.mark.asyncio
async def test_token_refresh_flow_and_expiry(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """User Journey: Refresh access token -> Receives later expiration time; expired token rejected."""
    user = await create_test_user(
        db=db_session,
        password="ValidPassword123!",
    )

    # 1. Login to get initial tokens
    login_res = await async_client.post(
        "/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    initial_tokens = login_res.json()
    initial_access_payload = decode_token(initial_tokens["access_token"])

    # 2. Call /auth/refresh
    refresh_res = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": initial_tokens["refresh_token"]},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    new_access_payload = decode_token(new_tokens["access_token"])
    assert new_access_payload["exp"] >= initial_access_payload["exp"]

    # 3. Expired refresh token returns 401
    expired_refresh = create_refresh_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=-30),
    )
    expired_res = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": expired_refresh},
    )
    assert expired_res.status_code == 401
    assert "expired" in expired_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_role_change_takes_effect_on_refresh(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Architectural Proof: Updating user role in DB takes effect upon /auth/refresh."""
    user = await create_test_user(
        db=db_session,
        role=RoleEnum.resident,
        password="ValidPassword123!",
    )

    # 1. Login as resident
    login_res = await async_client.post(
        "/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    initial_tokens = login_res.json()
    initial_payload = decode_token(initial_tokens["access_token"])
    assert initial_payload["role"] == "resident"

    # 2. Modify user role directly in DB to volunteer
    user.role = RoleEnum.volunteer
    await db_session.commit()

    # 3. Refresh token
    ref_res = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": initial_tokens["refresh_token"]},
    )
    assert ref_res.status_code == 200
    ref_tokens = ref_res.json()

    # 4. Decode new access token: MUST reflect updated 'volunteer' role
    updated_payload = decode_token(ref_tokens["access_token"])
    assert updated_payload["role"] == "volunteer"
