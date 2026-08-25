"""GuardianLink self-referential association model between residents and guardians."""

import enum
import uuid
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class GuardianPriorityEnum(str, enum.Enum):
    """Guardian escalation priority order."""
    primary = "primary"
    secondary = "secondary"


class ConsentStatusEnum(str, enum.Enum):
    """Guardian linkage consent status.

    CRITICAL PRIVACY NOTE:
    Any notification or escalation query MUST filter on `consent_status == accepted`.
    Guardians whose status is 'pending' or 'declined' MUST NOT receive SOS alerts
    or confidential resident location info.
    """
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class GuardianLink(Base):
    """Self-referential link table connecting a Resident to their designated Guardians."""
    __tablename__ = "guardian_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign keys pointing to users table
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    resident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    priority: Mapped[GuardianPriorityEnum] = mapped_column(
        Enum(GuardianPriorityEnum, name="guardian_priority_enum"),
        nullable=False,
    )
    consent_status: Mapped[ConsentStatusEnum] = mapped_column(
        Enum(ConsentStatusEnum, name="consent_status_enum"),
        default=ConsentStatusEnum.pending,
        server_default=text("'pending'"),
        nullable=False,
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

    # Disambiguated relationships with explicit foreign_keys
    guardian: Mapped["User"] = relationship("User", foreign_keys=[guardian_id])
    resident: Mapped["User"] = relationship("User", foreign_keys=[resident_id])

    __table_args__ = (
        # Check constraint: a user cannot be their own guardian
        CheckConstraint("guardian_id != resident_id", name="ck_guardian_not_self"),
        # Unique constraint: prevent duplicate guardian-resident pairings
        UniqueConstraint("guardian_id", "resident_id", name="uq_guardian_resident_pair"),
        # Partial unique index: exactly one primary guardian per resident
        Index(
            "uq_one_primary_guardian_per_resident",
            "resident_id",
            unique=True,
            postgresql_where=text("priority = 'primary'"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<GuardianLink id={self.id} resident_id={self.resident_id} "
            f"guardian_id={self.guardian_id} priority={self.priority.value} "
            f"consent={self.consent_status.value}>"
        )


# Import User for type annotations
from app.models.user import User  # noqa: E402
