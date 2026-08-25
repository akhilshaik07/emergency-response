"""SecurityProfile model extending User for community security personnel."""

import uuid
from datetime import time
from typing import Optional
from sqlalchemy import (
    String,
    Time,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class SecurityProfile(Base):
    """Profile table extending User with security credentials and shift timing."""
    __tablename__ = "security_profiles"

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

    # Optional block assignment (SET NULL preserves staff record if block is modified or reorganized)
    assigned_block_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("blocks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Employee ID scoped per society
    employee_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Structured shift timing (Time types enable SQL-level on-shift queries rather than string parsing)
    shift_start: Mapped[Optional[time]] = mapped_column(
        Time,
        nullable=True,
    )
    shift_end: Mapped[Optional[time]] = mapped_column(
        Time,
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
    user: Mapped["User"] = relationship("User", back_populates="security_profile")
    society: Mapped["Society"] = relationship("Society", back_populates="security_staff")
    assigned_block: Mapped[Optional["Block"]] = relationship("Block", backref="assigned_security_staff")

    # Composite uniqueness: employee_id is unique per society, not globally
    __table_args__ = (
        UniqueConstraint("society_id", "employee_id", name="uq_society_employee_id"),
    )

    def __repr__(self) -> str:
        return f"<SecurityProfile id={self.id} user_id={self.user_id} emp_id='{self.employee_id}'>"


# Import for type annotations
from app.models.user import User  # noqa: E402
from app.models.society import Society, Block  # noqa: E402
