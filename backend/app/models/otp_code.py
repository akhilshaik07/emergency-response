"""OtpCode model for registration and sensitive action verification."""

import enum
import uuid
from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Enum,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base


class OtpPurposeEnum(str, enum.Enum):
    """Purpose scoping for one-time passwords."""
    registration = "registration"
    password_reset = "password_reset"


class OtpCode(Base):
    """Stores hashed OTP codes and verification attempt metadata.

    SECURITY NOTE:
    1. Keyed by `phone`, not `user_id`, because registration OTPs occur before a User row exists.
    2. `code_hash` stores a cryptographically secure hash of the OTP (never plaintext).
    3. Scoped by `purpose` to prevent replay attacks across different workflows.
    4. `attempts` tracks verification attempts to lock out brute-force attacks.
    5. `consumed_at` enforces strict single-use consumption.
    """
    __tablename__ = "otp_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    phone: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )

    code_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    purpose: Mapped[OtpPurposeEnum] = mapped_column(
        Enum(OtpPurposeEnum, name="otp_purpose_enum"),
        default=OtpPurposeEnum.registration,
        nullable=False,
    )

    expires_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    consumed_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<OtpCode id={self.id} phone='{self.phone}' purpose={self.purpose.value} attempts={self.attempts}>"
