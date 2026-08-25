"""Location hierarchy models: Society, Block, and Flat."""

import enum
import uuid
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    String,
    Text,
    Integer,
    Numeric,
    DateTime,
    Enum,
    ForeignKey,
    UniqueConstraint,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class OccupancyStatusEnum(str, enum.Enum):
    """Flat occupancy status enum.

    Native PostgreSQL database enum constraint ensuring data integrity for residential units.
    """
    owner = "owner"
    tenant = "tenant"
    vacant = "vacant"


class Society(Base):
    """Gated community / residential society entity."""
    __tablename__ = "societies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    # Fixed-precision Numeric avoids floating-point drift during geospatial proximity calculations
    latitude: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=7),
        nullable=False,
    )
    longitude: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=7),
        nullable=False,
    )
    # TODO: Application validation layer must enforce non-null license before a society is set to active status
    rwa_license_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    # Each society has an initial administrative user
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    # response_window_seconds: Configurable SLA window (in seconds) used by the Celery/Redis escalation
    # engine to wait for guardian acknowledgment before escalating an SOS alert to security/volunteers.
    response_window_seconds: Mapped[int] = mapped_column(
        Integer,
        default=120,
        server_default=text("120"),
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
    admin: Mapped["User"] = relationship("User", foreign_keys=[admin_id])
    blocks: Mapped[List["Block"]] = relationship(
        "Block",
        back_populates="society",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    volunteers: Mapped[List["VolunteerProfile"]] = relationship(
        "VolunteerProfile",
        back_populates="society",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    security_staff: Mapped[List["SecurityProfile"]] = relationship(
        "SecurityProfile",
        back_populates="society",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Society id={self.id} name='{self.name}'>"


class Block(Base):
    """Building / Tower / Sector block within a society."""
    __tablename__ = "blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    # CASCADE DELETION NOTE: If a society is purged, all child blocks have no independent meaning
    # and must be cleaned up in cascade to avoid orphaned location nodes.
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("societies.id", ondelete="CASCADE"),
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
    society: Mapped["Society"] = relationship("Society", back_populates="blocks")
    flats: Mapped[List["Flat"]] = relationship(
        "Flat",
        back_populates="block",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Block id={self.id} name='{self.name}' society_id={self.society_id}>"


class Flat(Base):
    """Individual apartment / residential unit within a block."""
    __tablename__ = "flats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    unit_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    floor: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    # CASCADE DELETION NOTE: Flats cannot exist without their parent block.
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    occupancy_status: Mapped[OccupancyStatusEnum] = mapped_column(
        Enum(OccupancyStatusEnum, name="occupancy_status_enum"),
        default=OccupancyStatusEnum.vacant,
        server_default=text("'vacant'"),
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
    block: Mapped["Block"] = relationship("Block", back_populates="flats")

    # Composite unique constraint to prevent duplicate unit numbers within the same block
    __table_args__ = (
        UniqueConstraint("block_id", "unit_number", name="uq_block_unit_number"),
    )

    def __repr__(self) -> str:
        return f"<Flat id={self.id} unit='{self.unit_number}' block_id={self.block_id}>"


# Import related models for type resolution in relationships
from app.models.user import User  # noqa: E402
from app.models.volunteer import VolunteerProfile  # noqa: E402
from app.models.security_staff import SecurityProfile  # noqa: E402
