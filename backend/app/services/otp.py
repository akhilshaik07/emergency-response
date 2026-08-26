"""OTP generation, hashing, rate limiting, and verification service."""

import hmac
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.otp_code import OtpCode, OtpPurposeEnum

logger = logging.getLogger("app.otp")


class OtpService:
    """Service abstraction for generating, hashing, and dispatching OTP codes.

    PRODUCTION INTEGRATION PATH:
    In development mode, `send_otp()` logs to server logs for verification.
    In production, this abstraction is swapped with Twilio Verify / SMS Gateway
    without modifying endpoint or verification logic.
    """

    @staticmethod
    def generate_otp_code() -> str:
        """Generate a cryptographically secure 6-digit numeric OTP code."""
        code_num = secrets.randbelow(1_000_000)
        return f"{code_num:06d}"

    @staticmethod
    def hash_otp_code(code: str) -> str:
        """Hash the OTP code using HMAC-SHA256 keyed with JWT secret."""
        key = settings.JWT_SECRET_KEY.encode("utf-8")
        h = hmac.new(key, code.encode("utf-8"), hashlib.sha256)
        return h.hexdigest()

    @staticmethod
    def verify_otp_code(plain_code: str, hashed_code: str) -> bool:
        """Secure constant-time comparison of OTP code against hash."""
        expected_hash = OtpService.hash_otp_code(plain_code)
        return hmac.compare_digest(expected_hash, hashed_code)

    @staticmethod
    def send_otp(phone: str, code: str, purpose: OtpPurposeEnum) -> None:
        """Dispatch OTP to destination.

        SECURITY NOTE:
        This server log is strictly for development/testing visibility.
        The OTP code is NEVER returned in API responses.
        """
        logger.info(f"[DEV-OTP] OTP code for {phone} (purpose={purpose.value}): {code}")
        # Prominent console banner for local developer visibility
        print(
            f"\n======================================================\n"
            f" [DEV-OTP] Verification Code for {phone}\n"
            f" Purpose: {purpose.value}\n"
            f" CODE:    {code}\n"
            f"======================================================\n",
            flush=True,
        )



async def check_otp_rate_limit(
    db: AsyncSession,
    phone: str,
    purpose: OtpPurposeEnum,
) -> None:
    """Enforce rate limits per phone number to prevent SMS-bombing and brute force.

    Rules:
    - Max 1 OTP request per 60 seconds.
    - Max 5 OTP requests per 1 hour.
    """
    now = datetime.now(timezone.utc)
    sixty_seconds_ago = now - timedelta(seconds=60)
    one_hour_ago = now - timedelta(hours=1)

    # 1. 60-second cooldown check
    recent_q = select(OtpCode).where(
        and_(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.created_at >= sixty_seconds_ago,
        )
    )
    recent_result = await db.execute(recent_q)
    if recent_result.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting another OTP.",
        )

    # 2. Hourly volume cap
    hourly_q = select(func.count(OtpCode.id)).where(
        and_(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.created_at >= one_hour_ago,
        )
    )
    hourly_count = (await db.execute(hourly_q)).scalar() or 0
    if hourly_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP requests per hour exceeded.",
        )


async def verify_and_consume_otp(
    db: AsyncSession,
    phone: str,
    code: str,
    purpose: OtpPurposeEnum,
    max_attempts: int = 5,
) -> OtpCode:
    """Verify and consume an OTP code. Shared across Registration and Password Reset flows.

    Enforces:
    - Expiration check
    - Attempt limit tracking & lockout on excess failed guesses
    - Secure code comparison
    - Single-use consumption (consumed_at)
    """
    now = datetime.now(timezone.utc)

    # Lookup most recent unconsumed code for this phone and purpose
    query = (
        select(OtpCode)
        .where(
            and_(
                OtpCode.phone == phone,
                OtpCode.purpose == purpose,
                OtpCode.consumed_at.is_(None),
            )
        )
        .order_by(OtpCode.created_at.desc())
    )
    result = await db.execute(query)
    otp_record = result.scalars().first()

    # Check existence and expiration
    if otp_record is None or otp_record.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found. Please request a new one.",
        )

    # Increment attempts
    otp_record.attempts += 1

    # Check attempt limit / lockout
    if otp_record.attempts > max_attempts:
        otp_record.consumed_at = now  # Invalidate/kill the code
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum verification attempts exceeded. Please request a new OTP.",
        )

    # Compare code
    if not OtpService.verify_otp_code(code, otp_record.code_hash):
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    # Mark consumed
    otp_record.consumed_at = now
    await db.flush()
    return otp_record
