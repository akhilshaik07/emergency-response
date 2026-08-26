"""Pydantic request and response schemas for User, Authentication, and OTP verification."""

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from app.models.user import RoleEnum


class UserRegisterRequest(BaseModel):
    """Initial self-registration payload."""
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
        if v in (RoleEnum.admin, RoleEnum.superadmin):
            raise ValueError("Registration as 'admin' or 'superadmin' is not permitted via public registration")
        return v


class OtpRequestPayload(BaseModel):
    """Payload to request an OTP code for registration."""
    phone: str = Field(..., min_length=5, max_length=32, description="International phone number format")
    email: Optional[EmailStr] = None


class OtpVerifyPayload(BaseModel):
    """Payload to verify OTP code and finalize user registration."""
    phone: str = Field(..., min_length=5, max_length=32)
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    email: EmailStr
    password: str = Field(..., min_length=8)
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
        if v in (RoleEnum.admin, RoleEnum.superadmin):
            raise ValueError("Registration as 'admin' or 'superadmin' is not permitted via public registration")
        return v


class PasswordResetRequestPayload(BaseModel):
    """Payload to request an OTP code for password reset."""
    identifier: str = Field(..., min_length=3, max_length=255, description="Email address or phone number")


class PasswordResetVerifyPayload(BaseModel):
    """Payload to verify OTP code and complete password reset."""
    identifier: str = Field(..., min_length=3, max_length=255, description="Email address or phone number")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    new_password: str = Field(..., min_length=8, description="New password, minimum 8 characters")

    @field_validator("new_password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
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


class RefreshTokenRequest(BaseModel):
    """Payload to exchange a refresh token for new session tokens."""
    refresh_token: str = Field(..., min_length=1)


class UserUpdateRequest(BaseModel):
    """Self-update payload for authenticated user."""
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=5, max_length=32)
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """Public representation of a User entity (never includes hashed_password)."""
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


class MessageResponse(BaseModel):
    """Standard generic operational message response."""
    message: str
