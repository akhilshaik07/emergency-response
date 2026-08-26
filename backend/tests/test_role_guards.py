"""End-to-end integration tests for Role-Based Access Control and Society Scope Authorization."""

import pytest
import httpx
import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.user import User, RoleEnum
from app.api.deps import require_role
from tests.conftest import create_test_user, create_test_society, get_auth_headers

# Register a dedicated role-guarded test route
role_guard_test_router = APIRouter(prefix="/guard-tests", tags=["GuardTests"])


@role_guard_test_router.get("/admin-and-superadmin-only")
async def admin_only_action(
    current_user: User = Depends(require_role(RoleEnum.admin, RoleEnum.superadmin)),
):
    return {"message": f"Authorized for {current_user.email} with role {current_user.role.value}"}


app.include_router(role_guard_test_router)


@pytest.mark.asyncio
async def test_require_role_rejection_and_acceptance(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Permission Check: require_role correctly enforces role boundaries."""
    resident = await create_test_user(db=db_session, role=RoleEnum.resident)
    admin = await create_test_user(db=db_session, role=RoleEnum.admin)
    superadmin = await create_test_user(db=db_session, role=RoleEnum.superadmin)

    # 1. Unauthenticated request -> 401 Unauthorized (not 403)
    unauth_res = await async_client.get("/guard-tests/admin-and-superadmin-only")
    assert unauth_res.status_code == 401

    # 2. Resident request -> 403 Forbidden
    res_headers = await get_auth_headers(async_client, resident.email, resident.plain_password_for_test)
    res_response = await async_client.get("/guard-tests/admin-and-superadmin-only", headers=res_headers)
    assert res_response.status_code == 403
    assert "Forbidden" in res_response.json()["detail"]

    # 3. Admin request -> 200 OK
    admin_headers = await get_auth_headers(async_client, admin.email, admin.plain_password_for_test)
    admin_response = await async_client.get("/guard-tests/admin-and-superadmin-only", headers=admin_headers)
    assert admin_response.status_code == 200

    # 4. Superadmin request -> 200 OK
    super_headers = await get_auth_headers(async_client, superadmin.email, superadmin.plain_password_for_test)
    super_response = await async_client.get("/guard-tests/admin-and-superadmin-only", headers=super_headers)
    assert super_response.status_code == 200


@pytest.mark.asyncio
async def test_require_society_scope_authorization_scenarios(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Permission Check: require_society_scope authorizes owner and superadmin, rejects other admins and residents."""
    admin_a = await create_test_user(db=db_session, role=RoleEnum.admin)
    admin_b = await create_test_user(db=db_session, role=RoleEnum.admin)
    resident = await create_test_user(db=db_session, role=RoleEnum.resident)
    superadmin = await create_test_user(db=db_session, role=RoleEnum.superadmin)

    # Society 1 owned by Admin A
    society_1 = await create_test_society(db=db_session, admin_user=admin_a, name="Society Alpha")
    # Society 2 owned by Admin B
    society_2 = await create_test_society(db=db_session, admin_user=admin_b, name="Society Beta")

    headers_admin_a = await get_auth_headers(async_client, admin_a.email, admin_a.plain_password_for_test)
    headers_admin_b = await get_auth_headers(async_client, admin_b.email, admin_b.plain_password_for_test)
    headers_resident = await get_auth_headers(async_client, resident.email, resident.plain_password_for_test)
    headers_super = await get_auth_headers(async_client, superadmin.email, superadmin.plain_password_for_test)

    # 1. Unauthenticated request -> 401 Unauthorized
    unauth_patch = await async_client.patch(
        f"/societies/{society_1.id}",
        json={"name": "New Alpha Name"},
    )
    assert unauth_patch.status_code == 401

    # 2. Correct Admin (Admin A modifying Society 1) -> 200 OK
    patch_owner = await async_client.patch(
        f"/societies/{society_1.id}",
        headers=headers_admin_a,
        json={"name": "Society Alpha Updated"},
    )
    assert patch_owner.status_code == 200
    assert patch_owner.json()["name"] == "Society Alpha Updated"

    # 3. Wrong Admin (Admin B modifying Society 1) -> 403 Forbidden (NOT 404)
    patch_wrong_admin = await async_client.patch(
        f"/societies/{society_1.id}",
        headers=headers_admin_b,
        json={"name": "Hacked Alpha"},
    )
    assert patch_wrong_admin.status_code == 403
    assert "Forbidden" in patch_wrong_admin.json()["detail"]

    # 4. Plain Resident modifying Society 1 -> 403 Forbidden
    patch_resident = await async_client.patch(
        f"/societies/{society_1.id}",
        headers=headers_resident,
        json={"name": "Resident Alpha"},
    )
    assert patch_resident.status_code == 403

    # 5. Nonexistent Society ID -> 404 Not Found
    random_society_id = uuid.uuid4()
    patch_nonexistent = await async_client.patch(
        f"/societies/{random_society_id}",
        headers=headers_admin_a,
        json={"name": "Ghost Society"},
    )
    assert patch_nonexistent.status_code == 404
    assert "not found" in patch_nonexistent.json()["detail"].lower()

    # 6. Superadmin Override (Superadmin modifying Society 2 owned by Admin B) -> 200 OK
    patch_super = await async_client.patch(
        f"/societies/{society_2.id}",
        headers=headers_super,
        json={"response_window_seconds": 300},
    )
    assert patch_super.status_code == 200
    assert patch_super.json()["response_window_seconds"] == 300

    # 7. Superadmin Delete Override on Society 2
    del_super = await async_client.request(
        "DELETE",
        f"/societies/{society_2.id}",
        headers=headers_super,
        json={"confirmation_name": society_2.name},
    )
    assert del_super.status_code == 200
    assert "deleted" in del_super.json()["message"].lower()
