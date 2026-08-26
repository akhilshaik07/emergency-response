"""Integration tests for Auth, User CRUD, and Society CRUD API endpoints."""

import pytest
import httpx
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.main import app
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password, create_access_token
from app.models.user import User, RoleEnum
from app.models.society import Society

BASE_URL = "http://testserver"

API_TEST_EMAILS = [
    "user.alpha@example.com",
    "user.bravo@example.com",
    "user.charlie@example.com",
]

test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


async def clean_test_data():
    async with TestSessionLocal() as session:
        users = (await session.execute(select(User).where(User.email.in_(API_TEST_EMAILS)))).scalars().all()
        user_ids = [u.id for u in users]
        if user_ids:
            socs = (await session.execute(select(Society).where(Society.admin_id.in_(user_ids)))).scalars().all()
            for s in socs:
                await session.delete(s)
            for u in users:
                await session.delete(u)
            await session.commit()


@pytest.mark.asyncio
async def test_user_login_and_credential_enumeration_defense():
    await clean_test_data()
    try:
        # Create test user directly in database
        async with TestSessionLocal() as session:
            user = User(
                email="user.alpha@example.com",
                phone="+919999900001",
                hashed_password=hash_password("CorrectPassword123!"),
                role=RoleEnum.resident,
                is_active=True,
            )
            session.add(user)
            await session.commit()

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            # 1. Login with correct email + password
            login_email = await client.post(
                "/auth/login",
                json={"email": "user.alpha@example.com", "password": "CorrectPassword123!"},
            )
            assert login_email.status_code == 200
            token_data = login_email.json()
            assert "access_token" in token_data
            assert "refresh_token" in token_data
            assert token_data["token_type"] == "bearer"

            # 2. Login with correct phone + password
            login_phone = await client.post(
                "/auth/login",
                json={"phone": "+919999900001", "password": "CorrectPassword123!"},
            )
            assert login_phone.status_code == 200

            # 3. Wrong password
            wrong_pwd = await client.post(
                "/auth/login",
                json={"email": "user.alpha@example.com", "password": "WrongPassword!"},
            )
            assert wrong_pwd.status_code == 401

            # 4. Non-existent email
            non_existent = await client.post(
                "/auth/login",
                json={"email": "nonexistent@example.com", "password": "AnyPassword123!"},
            )
            assert non_existent.status_code == 401

            # 5. Verify error message wording is 100% identical (prevents enumeration)
            assert wrong_pwd.json()["detail"] == non_existent.json()["detail"]
            assert wrong_pwd.json()["detail"] == "Incorrect email/phone or password."
    finally:
        await clean_test_data()


@pytest.mark.asyncio
async def test_user_me_profile_update_and_soft_delete():
    await clean_test_data()
    try:
        # Create active user
        async with TestSessionLocal() as session:
            user = User(
                email="user.alpha@example.com",
                phone="+919999900001",
                hashed_password=hash_password("Password123!"),
                role=RoleEnum.resident,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            user_id = user.id

        token = create_access_token(str(user_id), role=RoleEnum.resident.value)
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            # 1. GET /users/me
            me_res = await client.get("/users/me", headers=headers)
            assert me_res.status_code == 200
            me_data = me_res.json()
            assert me_data["email"] == "user.alpha@example.com"
            assert "hashed_password" not in me_data

            # 2. PATCH /users/me (update phone)
            patch_res = await client.patch(
                "/users/me",
                headers=headers,
                json={"phone": "+919999900099"},
            )
            assert patch_res.status_code == 200
            assert patch_res.json()["phone"] == "+919999900099"

            # 3. DELETE /users/me (soft delete)
            del_res = await client.delete("/users/me", headers=headers)
            assert del_res.status_code == 200
            assert "deactivated" in del_res.json()["message"]

            # 4. Verify in DB that row still exists but is_active is False
            async with TestSessionLocal() as session:
                db_user = (await session.execute(select(User).where(User.email == "user.alpha@example.com"))).scalar_one()
                assert db_user is not None
                assert db_user.is_active is False

            # 5. Subsequent request with token fails (user is deactivated)
            me_after_del = await client.get("/users/me", headers=headers)
            assert me_after_del.status_code == 401

            # 6. Subsequent login fails
            login_after_del = await client.post(
                "/auth/login",
                json={"email": "user.alpha@example.com", "password": "Password123!"},
            )
            assert login_after_del.status_code == 401
    finally:
        await clean_test_data()


@pytest.mark.asyncio
async def test_society_crud_ownership_and_guarded_delete():
    await clean_test_data()
    try:
        # Create User A and User B in DB
        async with TestSessionLocal() as session:
            user_a = User(email="user.alpha@example.com", phone="+919999900001", hashed_password=hash_password("Pass123!"), role=RoleEnum.admin, is_active=True)
            user_b = User(email="user.bravo@example.com", phone="+919999900002", hashed_password=hash_password("Pass123!"), role=RoleEnum.resident, is_active=True)
            session.add_all([user_a, user_b])
            await session.commit()
            await session.refresh(user_a)
            await session.refresh(user_b)
            user_a_id = user_a.id
            user_b_id = user_b.id

        token_a = create_access_token(str(user_a_id), role=RoleEnum.admin.value)
        token_b = create_access_token(str(user_b_id), role=RoleEnum.resident.value)
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            # 1. User A creates a Society
            soc_payload = {
                "name": "Grand Orchids Residency",
                "address": "77 Lotus Boulevard, Sector 15",
                "latitude": 13.0827,
                "longitude": 80.2707,
                "rwa_license_number": "RWA-2026-901",
                "response_window_seconds": 90,
            }
            create_res = await client.post("/societies", headers=headers_a, json=soc_payload)
            assert create_res.status_code == 201
            soc_data = create_res.json()
            soc_id = soc_data["id"]
            assert soc_data["name"] == "Grand Orchids Residency"
            assert float(soc_data["latitude"]) == 13.0827

            # 2. User B can view society (open read check)
            get_res = await client.get(f"/societies/{soc_id}", headers=headers_b)
            assert get_res.status_code == 200
            assert get_res.json()["name"] == "Grand Orchids Residency"

            # 3. User B attempts PATCH -> 403 Forbidden (ownership check)
            patch_b = await client.patch(
                f"/societies/{soc_id}",
                headers=headers_b,
                json={"name": "Hacked Name"},
            )
            assert patch_b.status_code == 403

            # 4. User A performs PATCH -> 200 OK
            patch_a = await client.patch(
                f"/societies/{soc_id}",
                headers=headers_a,
                json={"name": "Grand Orchids Heights", "response_window_seconds": 60},
            )
            assert patch_a.status_code == 200
            assert patch_a.json()["name"] == "Grand Orchids Heights"
            assert patch_a.json()["response_window_seconds"] == 60

            # 5. User B attempts DELETE -> 403 Forbidden
            del_b = await client.request(
                "DELETE",
                f"/societies/{soc_id}",
                headers=headers_b,
                json={"confirmation_name": "Grand Orchids Heights"},
            )
            assert del_b.status_code == 403

            # 6. User A attempts DELETE with mismatched confirmation name -> 400 Bad Request
            del_mismatch = await client.request(
                "DELETE",
                f"/societies/{soc_id}",
                headers=headers_a,
                json={"confirmation_name": "Wrong Name"},
            )
            assert del_mismatch.status_code == 400
            assert "mismatch" in del_mismatch.json()["detail"].lower()

            # 7. User A attempts DELETE with correct confirmation name -> 200 OK
            del_success = await client.request(
                "DELETE",
                f"/societies/{soc_id}",
                headers=headers_a,
                json={"confirmation_name": "Grand Orchids Heights"},
            )
            assert del_success.status_code == 200
            assert "deleted" in del_success.json()["message"].lower()

            # 8. Confirm Society is deleted in DB
            async with TestSessionLocal() as session:
                soc_check = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one_or_none()
                assert soc_check is None
    finally:
        await clean_test_data()
