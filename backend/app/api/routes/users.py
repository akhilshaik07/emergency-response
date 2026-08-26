"""User profile management endpoints."""

from typing import Annotated, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.user import UserUpdateRequest, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Retrieve profile data for the currently authenticated user."""
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current authenticated user profile",
)
async def update_my_profile(
    payload: UserUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Self-update email or phone for the current user.

    NOTE ON EXCLUSIONS:
    Password changes and role modifications are explicitly excluded from this endpoint.
    """
    # Check for email collision with other accounts if email is being updated
    if payload.email is not None and payload.email != current_user.email:
        email_conflict = await db.execute(
            select(User).where(and_(User.email == payload.email, User.id != current_user.id))
        )
        if email_conflict.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )
        current_user.email = payload.email

    # Check for phone collision with other accounts if phone is being updated
    if payload.phone is not None and payload.phone != current_user.phone:
        phone_conflict = await db.execute(
            select(User).where(and_(User.phone == payload.phone, User.id != current_user.id))
        )
        if phone_conflict.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this phone number already exists.",
            )
        current_user.phone = payload.phone

    if payload.is_active is not None:
        current_user.is_active = payload.is_active

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.delete(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Deactivate current user account (Soft Delete)",
)
async def delete_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dict[str, str]:
    """Soft-delete the user's account by marking `is_active = False`.

    SAFETY RATIONALE:
    Physical database deletion (hard delete) of user records is intentionally avoided
    to preserve safety audit logs, emergency contact records, and incident histories.
    """
    current_user.is_active = False
    await db.commit()
    return {"message": "User account has been deactivated successfully."}
