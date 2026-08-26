"""Society CRUD endpoints for gated community administration."""

import logging
import uuid
from typing import Annotated, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.models.society import Society
from app.schemas.society import (
    SocietyCreateRequest,
    SocietyUpdateRequest,
    SocietyDeleteRequest,
    SocietyResponse,
)

logger = logging.getLogger("app.societies")
router = APIRouter(prefix="/societies", tags=["Societies"])


@router.post(
    "",
    response_model=SocietyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new gated residential society",
)
async def create_society(
    payload: SocietyCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Society:
    """Create a new society with the authenticated user designated as society admin.

    TODO (TEMPORARY PERMISSIVENESS GAP):
    This endpoint currently allows ANY authenticated user to create a society and become its admin.
    In the next phase, this MUST be restricted using `require_role(RoleEnum.admin, RoleEnum.superadmin)`
    once full role guards are introduced.
    """
    society = Society(
        name=payload.name,
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        rwa_license_number=payload.rwa_license_number,
        admin_id=current_user.id,
        response_window_seconds=payload.response_window_seconds,
    )
    db.add(society)
    await db.commit()
    await db.refresh(society)
    logger.info(f"AUDIT: Society '{society.name}' (id={society.id}) created by admin user {current_user.id}")
    return society


@router.get(
    "/{society_id}",
    response_model=SocietyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get society details by ID",
)
async def get_society_by_id(
    society_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Society:
    """Retrieve details for a specific society.

    TODO (TEMPORARY PERMISSIVENESS GAP):
    Currently allows any authenticated user to view any society details.
    Will be scoped via `require_society_scope` in subsequent steps.
    """
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()

    if society is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Society not found.",
        )
    return society


@router.patch(
    "/{society_id}",
    response_model=SocietyResponse,
    status_code=status.HTTP_200_OK,
    summary="Update society details",
)
async def update_society(
    society_id: uuid.UUID,
    payload: SocietyUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Society:
    """Update society metadata.

    OWNERSHIP RESTRICTION:
    Only the assigned `admin_id` of the society can modify its properties.
    """
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()

    if society is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Society not found.",
        )

    # Ownership check
    if society.admin_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only the society administrator can update this society.",
        )

    # Apply partial updates
    if payload.name is not None:
        society.name = payload.name
    if payload.address is not None:
        society.address = payload.address
    if payload.latitude is not None:
        society.latitude = payload.latitude
    if payload.longitude is not None:
        society.longitude = payload.longitude
    if payload.rwa_license_number is not None:
        society.rwa_license_number = payload.rwa_license_number
    if payload.response_window_seconds is not None:
        society.response_window_seconds = payload.response_window_seconds

    await db.commit()
    await db.refresh(society)
    logger.info(f"AUDIT: Society '{society.name}' (id={society.id}) updated by admin user {current_user.id}")
    return society


@router.delete(
    "/{society_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a society (guarded with confirmation name)",
)
async def delete_society(
    society_id: uuid.UUID,
    payload: SocietyDeleteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Dict[str, str]:
    """Permanently delete a society.

    SAFETY AND AUDITING GUARDS:
    1. Ownership check: strictly restricted to the society's admin.
    2. Confirmation check: client must send `confirmation_name == society.name`.
    3. Action is recorded to application audit logs.
    """
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()

    if society is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Society not found.",
        )

    # Ownership check
    if society.admin_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only the society administrator can delete this society.",
        )

    # Confirmation name match check
    if payload.confirmation_name != society.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confirmation name mismatch. Expected '{society.name}', got '{payload.confirmation_name}'.",
        )

    society_name = society.name
    # Audit log entry before deletion
    logger.warning(
        f"CRITICAL AUDIT: Society '{society_name}' (id={society.id}) DELETED by admin user {current_user.id} ({current_user.email})"
    )

    await db.delete(society)
    await db.commit()
    return {"message": f"Society '{society_name}' has been permanently deleted."}
