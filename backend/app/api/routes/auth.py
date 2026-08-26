"""Authentication endpoints: user registration and login."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.user import UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register_user(
    payload: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Register a new resident, volunteer, guardian, or security user.

    NOTE ON TOKEN ISSUANCE:
    Tokens are intentionally NOT auto-issued on registration. In later phases,
    phone/OTP verification will sit between registration and initial session login.
    """
    # Check for existing email or phone conflict
    conflict_query = select(User).where(
        or_(User.email == payload.email, User.phone == payload.phone)
    )
    conflict_result = await db.execute(conflict_query)
    existing_user = conflict_result.scalar_one_or_none()

    if existing_user is not None:
        if existing_user.email == payload.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this phone number already exists.",
            )

    # Hash password and create user
    hashed_pwd = hash_password(payload.password)
    user = User(
        email=payload.email,
        phone=payload.phone,
        hashed_password=hashed_pwd,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT tokens",
)
async def login_user(
    payload: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate via email or phone + password.

    SECURITY NOTE ON ERROR MESSAGES:
    The failure error message is deliberately identical for non-existent users,
    inactive accounts, and incorrect passwords to prevent credential enumeration attacks.
    """
    query = select(User)
    if payload.email and payload.phone:
        query = query.where(or_(User.email == payload.email, User.phone == payload.phone))
    elif payload.email:
        query = query.where(User.email == payload.email)
    elif payload.phone:
        query = query.where(User.phone == payload.phone)

    result = await db.execute(query)
    user = result.scalar_one_or_none()

    # Unified failure message to prevent email/phone enumeration
    generic_auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email/phone or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        raise generic_auth_error

    if not user.is_active:
        raise generic_auth_error

    if not verify_password(payload.password, user.hashed_password):
        raise generic_auth_error

    # Generate tokens
    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
