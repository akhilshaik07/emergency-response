"""Pydantic request and response schemas for Society domain entity."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SocietyCreateRequest(BaseModel):
    """Payload for creating a new gated society."""
    name: str = Field(..., min_length=2, max_length=255, description="Official name of the residential society")
    address: str = Field(..., min_length=5, description="Full street address")
    latitude: Decimal = Field(..., ge=-90, le=90, description="Geographic latitude coordinate")
    longitude: Decimal = Field(..., ge=-180, le=180, description="Geographic longitude coordinate")
    rwa_license_number: Optional[str] = Field(None, max_length=100, description="RWA registration number")
    response_window_seconds: int = Field(default=120, ge=10, le=3600, description="Escalation SLA timeout in seconds")


class SocietyUpdateRequest(BaseModel):
    """Payload for partially updating society details.

    SECURITY DECISION:
    `admin_id` is deliberately EXCLUDED from generic PATCH updates. Transferring society
    administrative ownership requires an explicit, multi-party ownership transfer flow.
    """
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    address: Optional[str] = Field(None, min_length=5)
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)
    rwa_license_number: Optional[str] = Field(None, max_length=100)
    response_window_seconds: Optional[int] = Field(None, ge=10, le=3600)


class SocietyDeleteRequest(BaseModel):
    """Guarded deletion confirmation payload.

    SAFETY NOTE:
    Because deleting a society cascades through all blocks, flats, and profiles,
    the client MUST echo the exact society name to confirm deletion intent.
    """
    confirmation_name: str = Field(..., description="Must match the exact name of the society to confirm deletion")


class SocietyResponse(BaseModel):
    """Representation of a Society entity returned to clients."""
    id: uuid.UUID
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    rwa_license_number: Optional[str] = None
    admin_id: uuid.UUID
    response_window_seconds: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
