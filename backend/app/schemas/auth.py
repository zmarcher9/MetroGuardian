"""
Pydantic schemas for auth (signup, login, token, user response).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="At least 8 characters")

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
