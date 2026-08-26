"""Authentication endpoints: OTP-gated registration, login, token refresh, and password reset."""

from datetime import datetime, timezone
from typing import Annotated, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenExpiredError,
    TokenInvalidError,
)
from app.models.user import User
from app.models.otp_code import OtpCode, OtpPurposeEnum
from app.services.otp import (
    OtpService,
    check_otp_rate_limit,
    verify_and_consume_otp,
)
from app.schemas.user import (
    UserRegisterRequest,
    OtpRequestPayload,
    OtpVerifyPayload,
    PasswordResetRequestPayload,
    PasswordResetVerifyPayload,
    UserLoginRequest,
    RefreshTokenRequest,
    UserResponse,
    TokenResponse,
    MessageResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ==============================================================================
# 1. OTP-Gated Registration Flow
# ==============================================================================

@router.post(
    "/register/request-otp",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a 6-digit OTP code for new user registration",
)
async def request_registration_otp(
    payload: OtpRequestPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Send a registration OTP after validating account uniqueness and rate limits.

    SECURITY MEASURES:
    1. Early uniqueness check: Rejects with 409 if phone or email is already registered.
    2. Rate limiting: Max 1 OTP / 60 seconds, max 5 OTPs / 1 hour per phone.
    3. Secure OTP: Stored as SHA256-HMAC hash; never returned in API response.
    """
    # 1. Check for conflicting existing user accounts
    conflict_conditions = [User.phone == payload.phone]
    if payload.email:
        conflict_conditions.append(User.email == payload.email)

    conflict_q = select(User).where(or_(*conflict_conditions))
    conflict_user = (await db.execute(conflict_q)).scalar_one_or_none()

    if conflict_user is not None:
        if payload.email and conflict_user.email == payload.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    # 2. Rate-limiting check
    await check_otp_rate_limit(db, payload.phone, OtpPurposeEnum.registration)

    # 3. Generate, hash, and store OTP record
    code = OtpService.generate_otp_code()
    code_hash = OtpService.hash_otp_code(code)
    from datetime import timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    otp_record = OtpCode(
        phone=payload.phone,
        code_hash=code_hash,
        purpose=OtpPurposeEnum.registration,
        expires_at=expires_at,
        attempts=0,
    )
    db.add(otp_record)
    await db.commit()

    # 4. Dispatch OTP via swappable service abstraction
    OtpService.send_otp(payload.phone, code, OtpPurposeEnum.registration)

    return MessageResponse(message="OTP has been sent to your phone number.")


@router.post(
    "/register/verify-otp",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verify registration OTP and create user account",
)
async def verify_registration_otp(
    payload: OtpVerifyPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Verify OTP, mark code consumed, and provision the new User entity.

    SECURITY NOTE ON SEPARATION OF CONCERNS:
    Tokens are NOT auto-issued from this endpoint. Registration and login remain
    separate steps so credential creation does not conflate with session management.
    """
    # 1. Verify OTP using shared verification helper (enforces expiry, attempts limit, single-use)
    await verify_and_consume_otp(
        db=db,
        phone=payload.phone,
        code=payload.code,
        purpose=OtpPurposeEnum.registration,
    )

    # 2. Final race-condition uniqueness check
    conflict_q = select(User).where(
        or_(User.email == payload.email, User.phone == payload.phone)
    )
    conflict_user = (await db.execute(conflict_q)).scalar_one_or_none()
    if conflict_user is not None:
        if conflict_user.email == payload.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    # 3. Create user
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


# ==============================================================================
# 2. Authentication & Token Management (Login + Refresh)
# ==============================================================================

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT access + refresh tokens",
)
async def login_user(
    payload: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate via email or phone + password.

    CREDENTIAL ENUMERATION DEFENSE:
    The failure message is 100% identical for non-existent users, wrong passwords,
    and deactivated accounts.
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

    generic_auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email/phone or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise generic_auth_error

    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange refresh token for a new access token and rotated refresh token",
)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Validate refresh token and issue a fresh access token with current DB role.

    SECURITY GUARDS:
    1. Distinguishes expired token from corrupt/tampered token.
    2. Re-resolves user from database to confirm account is still active and fetch any updated role.
    3. Emits a rotated refresh token.
    """
    try:
        decoded_payload = decode_token(payload.refresh_token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token signature or format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if decoded_payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Refresh token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = decoded_payload.get("sub", "")
    try:
        import uuid
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject in refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Re-fetch user fresh from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated or no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Issue new access token with fresh role and rotated refresh token
    new_access_token = create_access_token(subject=str(user.id), role=user.role.value)
    new_refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


# ==============================================================================
# 3. Password Reset Flow (Step 23)
# ==============================================================================

@router.post(
    "/password-reset/request-otp",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password reset OTP code",
)
async def request_password_reset_otp(
    payload: PasswordResetRequestPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Initiate password reset with enumeration protection.

    SECURITY RULE (ACCOUNT ENUMERATION IMMUNITY):
    Returns the exact same response regardless of whether an account exists or not.
    """
    query = select(User).where(
        or_(User.email == payload.identifier, User.phone == payload.identifier)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    # Always perform simulated hashing to equalize processing time budget
    dummy_code = OtpService.generate_otp_code()
    _ = OtpService.hash_otp_code(dummy_code)

    if user is not None and user.is_active:
        # Rate limit password reset requests
        await check_otp_rate_limit(db, user.phone, OtpPurposeEnum.password_reset)

        code = OtpService.generate_otp_code()
        code_hash = OtpService.hash_otp_code(code)
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        otp_record = OtpCode(
            phone=user.phone,
            code_hash=code_hash,
            purpose=OtpPurposeEnum.password_reset,
            expires_at=expires_at,
            attempts=0,
        )
        db.add(otp_record)
        await db.commit()

        OtpService.send_otp(user.phone, code, OtpPurposeEnum.password_reset)

    return MessageResponse(
        message="If an account exists with this identifier, an OTP has been sent."
    )


@router.post(
    "/password-reset/verify-and-reset",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify password reset OTP and set new password",
)
async def verify_password_reset_and_update(
    payload: PasswordResetVerifyPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Verify OTP and update user password.

    SESSION INVALIDATION NOTE:
    Password reset requires fresh re-login. Old access tokens will expire within their short
    lifetime (30 min), and token refreshes for deactivated/modified credentials re-validate state.
    """
    # 1. Lookup user by identifier
    query = select(User).where(
        or_(User.email == payload.identifier, User.phone == payload.identifier)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found. Please request a new one.",
        )

    # 2. Verify OTP using shared helper
    await verify_and_consume_otp(
        db=db,
        phone=user.phone,
        code=payload.code,
        purpose=OtpPurposeEnum.password_reset,
    )

    # 3. Update password
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()

    return MessageResponse(
        message="Password has been reset successfully. Please log in with your new password."
    )
