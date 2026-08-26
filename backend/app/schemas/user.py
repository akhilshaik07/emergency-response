"""Pydantic request and response schemas for User and Authentication."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from app.models.user import RoleEnum


class UserRegisterRequest(BaseModel):
    """Public self-registration payload."""
    email: EmailStr
    phone: str = Field(..., min_length=5, max_length=32, description="International phone number format")
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    role: RoleEnum = RoleEnum.resident

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @field_validator("role")
    @classmethod
    def validate_public_registration_role(cls, v: RoleEnum) -> RoleEnum:
        # SECURITY DECISION: Admin and Superadmin roles cannot be provisioned via public self-registration.
        if v in (RoleEnum.admin, RoleEnum.superadmin):
            raise ValueError("Registration as 'admin' or 'superadmin' is not permitted via public registration")
        return v


class UserLoginRequest(BaseModel):
    """User authentication payload supporting email or phone identification."""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_identifier_present(self) -> "UserLoginRequest":
        if not self.email and not self.phone:
            raise ValueError("Either 'email' or 'phone' must be provided for login")
        return self


class UserUpdateRequest(BaseModel):
    """Self-update payload for authenticated user.

    SECURITY DECISION:
    `password` and `role` are deliberately EXCLUDED from this schema. Password changes
    require current-password confirmation flows, and role changes require administrative
    authorization rather than unconstrained self-service PATCH requests.
    """
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=5, max_length=32)
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """Public representation of a User entity.

    CRITICAL SECURITY RULE:
    `hashed_password` MUST NEVER be exposed in any response schema.
    """
    id: uuid.UUID
    email: EmailStr
    phone: str
    role: RoleEnum
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """JWT bearer token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
