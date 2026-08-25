"""VolunteerProfile model extending User for community volunteers."""

import enum
import uuid
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class VolunteerAvailabilityEnum(str, enum.Enum):
    """Volunteer availability status.

    SAFETY NOTE:
    Newly registered volunteers must always default to 'off_duty' so they do not
    receive live SOS alerts prior to vetting and manual shift sign-on.
    """
    available = "available"
    busy = "busy"
    off_duty = "off_duty"


class VolunteerProfile(Base):
    """Profile table extending User with volunteer qualifications and availability.

    NOTE ON 1:1 ENFORCEMENT:
    The unique=True constraint on user_id enforces exactly one VolunteerProfile per User.
    """
    __tablename__ = "volunteer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # 1:1 relationship with users table
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Scoped to one society
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # PostgreSQL native ARRAY allows indexed containment queries (e.g. ANY/overlap/contains)
    # for fast category-to-skill matching during emergency dispatch.
    skills: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default=text("'{}'::varchar[]"),
        nullable=False,
    )

    # SAFETY DEFAULT: 'off_duty' prevents unvetted or inactive volunteers from receiving live alerts
    availability_status: Mapped[VolunteerAvailabilityEnum] = mapped_column(
        Enum(VolunteerAvailabilityEnum, name="volunteer_availability_enum"),
        default=VolunteerAvailabilityEnum.off_duty,
        server_default=text("'off_duty'"),
        nullable=False,
    )

    # rating is intentionally nullable with no default (not 0 or 5) until earned
    rating: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=3, scale=2),
        nullable=True,
        default=None,
    )

    # CRITICAL DISPATCH GATE: Queries matching volunteers to incidents MUST filter on background_verified == True
    background_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="volunteer_profile")
    society: Mapped["Society"] = relationship("Society", back_populates="volunteers")

    def __repr__(self) -> str:
        return f"<VolunteerProfile id={self.id} user_id={self.user_id} status={self.availability_status.value}>"


# Import for type annotations
from app.models.user import User  # noqa: E402
from app.models.society import Society  # noqa: E402
