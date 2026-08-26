"""Shared test fixtures and database helpers for Phase 3 integration testing."""

import pytest
import pytest_asyncio
import httpx
import uuid
from decimal import Decimal
from typing import AsyncGenerator, Dict
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password
from app.models.user import User, RoleEnum
from app.models.society import Society
from app.models.otp_code import OtpCode

# Test engine using NullPool so connections do not cross event loop boundaries
test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session per test."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an asynchronous HTTP client configured with ASGITransport."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def clean_database_state():
    """Ensure database state is clean before and after each test run."""
    async with TestSessionLocal() as session:
        # Clean OTP codes
        await session.execute(delete(OtpCode))
        # Clean societies
        await session.execute(delete(Society))
        # Clean users
        await session.execute(delete(User))
        await session.commit()
    yield
    async with TestSessionLocal() as session:
        await session.execute(delete(OtpCode))
        await session.execute(delete(Society))
        await session.execute(delete(User))
        await session.commit()


# ==============================================================================
# Helper Factories & Authenticators
# ==============================================================================

async def create_test_user(
    db: AsyncSession,
    role: RoleEnum = RoleEnum.resident,
    email: str = None,
    phone: str = None,
    password: str = "Password123!",
    is_active: bool = True,
) -> User:
    """Helper factory to create users of any role directly in the database."""
    unique_suffix = uuid.uuid4().hex[:8]
    if email is None:
        email = f"user.{role.value}.{unique_suffix}@example.com"
    if phone is None:
        # Generate valid unique 10-digit number formatted internationally
        phone = f"+9198{uuid.uuid4().int % 100000000:08d}"

    user = User(
        email=email,
        phone=phone,
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # Store plaintext password on entity object for test login convenience
    user.plain_password_for_test = password
    return user


async def create_test_society(
    db: AsyncSession,
    admin_user: User,
    name: str = None,
) -> Society:
    """Helper factory to create societies directly in the database."""
    if name is None:
        name = f"Society {uuid.uuid4().hex[:6]}"

    society = Society(
        name=name,
        address="123 Harmony Street, District 4",
        latitude=Decimal("12.9716"),
        longitude=Decimal("77.5946"),
        admin_id=admin_user.id,
        response_window_seconds=120,
    )
    db.add(society)
    await db.commit()
    await db.refresh(society)
    return society


async def get_auth_headers(
    client: httpx.AsyncClient,
    identifier: str,
    password: str,
) -> Dict[str, str]:
    """Authenticate a test user via the real /auth/login endpoint and return Bearer auth headers."""
    payload = {"password": password}
    if "@" in identifier:
        payload["email"] = identifier
    else:
        payload["phone"] = identifier

    response = await client.post("/auth/login", json=payload)
    if response.status_code != 200:
        raise ValueError(f"Failed to authenticate user '{identifier}': {response.text}")

    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}
