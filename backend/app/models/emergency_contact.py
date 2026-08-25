"""EmergencyContact model for resident external/professional contacts."""

import enum
import uuid
from typing import Optional
from sqlalchemy import (
    String,
    DateTime,
    Enum,
    ForeignKey,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class ContactTypeEnum(str, enum.Enum):
    """Classification of external emergency contact."""
    medical = "medical"
    family = "family"
    legal = "legal"
    other = "other"


class ContactVerificationStatusEnum(str, enum.Enum):
    """Verification lifecycle of an emergency contact number.

    Includes 'pending' state for active OTP/call verification workflows in progress.
    """
    unverified = "unverified"
    pending = "pending"
    verified = "verified"


class EmergencyContact(Base):
    """External emergency contacts registered by a resident.

    NOTE ON DESIGN:
    1. Points directly at `User` (the resident), maintaining consistent FK referencing
       across the platform alongside `GuardianLink`.
    2. Phone number format validation is intentionally handled at the Pydantic API
       boundary rather than DB regex to accommodate international formats safely.
    """
    __tablename__ = "emergency_contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    resident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    phone: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    contact_type: Mapped[ContactTypeEnum] = mapped_column(
        Enum(ContactTypeEnum, name="contact_type_enum"),
        nullable=False,
    )

    verification_status: Mapped[ContactVerificationStatusEnum] = mapped_column(
        Enum(ContactVerificationStatusEnum, name="contact_verification_status_enum"),
        default=ContactVerificationStatusEnum.unverified,
        server_default=text("'unverified'"),
        nullable=False,
    )

    # Required for periodic re-verification reminders (e.g. prompt resident to verify every N months)
    last_verified_at: Mapped[Optional[DateTime]] = mapped_column(
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

    # Relationships
    resident: Mapped["User"] = relationship("User", foreign_keys=[resident_id], back_populates="emergency_contacts")

    def __repr__(self) -> str:
        return f"<EmergencyContact id={self.id} name='{self.name}' type={self.contact_type.value} status={self.verification_status.value}>"


# Import for type annotations
from app.models.user import User  # noqa: E402
