"""FastAPI request dependencies for authentication, role enforcement, and resource scoping."""

import uuid
from typing import Annotated, Callable, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_token, TokenExpiredError, TokenInvalidError
from app.models.user import User, RoleEnum
from app.models.society import Society

# HTTP Bearer scheme
security_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate the JWT Bearer token, returning the active User entity."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials. Invalid token signature or format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub", "")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID in token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Query database for user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(*allowed_roles: RoleEnum) -> Callable:
    """Dependency factory enforcing that the authenticated user possesses one of the allowed roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role(RoleEnum.admin, RoleEnum.superadmin))])
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            role_names = ", ".join(r.value for r in allowed_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: User role '{current_user.role.value}' is not authorized. Required: [{role_names}].",
            )
        return current_user

    return role_checker


async def require_society_scope(
    society_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Society:
    """Dependency enforcing that the authenticated user has administrative authority over a specific society.

    Authorization Rules:
    1. The target society MUST exist in the database (raises 404 if not found).
    2. Access is granted if `current_user.id == society.admin_id` OR `current_user.role == RoleEnum.superadmin`.
    3. Any other user (including admins of different societies or plain residents) is rejected with 403 Forbidden.

    SCOPE DECISION NOTE (FOLLOW-UP):
    This dependency strictly enforces WRITE / ADMINISTRATIVE authority.
    A broader, read-scoped variant (allowing residents/volunteers/guards belonging to the society)
    will be evaluated in Phase 4 once membership models and profiles are linked to societies.
    """
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()

    if society is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Society not found.",
        )

    # Superadmin has platform-wide access; otherwise caller must be the society's registered admin
    if current_user.role != RoleEnum.superadmin and society.admin_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have administrative authority over this society.",
        )

    return society
