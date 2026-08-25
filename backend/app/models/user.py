"""User authentication and base identity model."""

import enum
import uuid
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Enum, text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.base import Base


class RoleEnum(str, enum.Enum):
    """User authorization role enum.

    Native PostgreSQL database enum constraint ensuring role integrity across
    all insert/update operations.
    """
    resident = "resident"
    guardian = "guardian"
    volunteer = "volunteer"
    security = "security"
    admin = "admin"
    superadmin = "superadmin"


class User(Base):
    """Core identity and authentication table.

    NOTE ON DESIGN:
    Role-specific attributes (such as skills, badge numbers, flat assignments,
    or shift timings) intentionally DO NOT live on this table. They belong
    in dedicated per-role profile models (ResidentProfile, VolunteerProfile,
    SecurityProfile) to support users holding multiple concurrent roles
    (e.g., a resident who also serves as a community volunteer) and clean role
    transitions without polluting the core identity/auth schema.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[RoleEnum] = mapped_column(
        Enum(RoleEnum, name="role_enum"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
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
    resident_profile: Mapped[Optional["ResidentProfile"]] = relationship(
        "ResidentProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    volunteer_profile: Mapped[Optional["VolunteerProfile"]] = relationship(
        "VolunteerProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    security_profile: Mapped[Optional["SecurityProfile"]] = relationship(
        "SecurityProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    emergency_contacts: Mapped[List["EmergencyContact"]] = relationship(
        "EmergencyContact",
        foreign_keys="EmergencyContact.resident_id",
        back_populates="resident",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' phone='{self.phone}' role={self.role.value}>"


from app.models.resident import ResidentProfile  # noqa: E402
from app.models.volunteer import VolunteerProfile  # noqa: E402
from app.models.security_staff import SecurityProfile  # noqa: E402
from app.models.emergency_contact import EmergencyContact  # noqa: E402
