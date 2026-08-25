"""Models package exporting all domain entities for Alembic and application queries."""

from app.models.user import User, RoleEnum
from app.models.society import Society, Block, Flat, OccupancyStatusEnum
from app.models.resident import ResidentProfile, ResidentStatusEnum
from app.models.guardian_link import (
    GuardianLink,
    GuardianPriorityEnum,
    ConsentStatusEnum,
)

__all__ = [
    "User",
    "RoleEnum",
    "Society",
    "Block",
    "Flat",
    "OccupancyStatusEnum",
    "ResidentProfile",
    "ResidentStatusEnum",
    "GuardianLink",
    "GuardianPriorityEnum",
    "ConsentStatusEnum",
]
