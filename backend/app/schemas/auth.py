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


class RefreshRequest(BaseModel):
    """
    Body for mobile/native clients on POST /auth/refresh and /auth/logout.
    Web clients send neither - their refresh token lives only in the
    (cookie-jar-managed) mg_rt cookie.
    """

    refresh_token: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """
    Returned only to mobile/native clients (X-Client-Type: mobile). Web
    clients get tokens exclusively via httpOnly cookies, never in the body -
    putting a token here too would make it readable by any XSS on the page,
    defeating the point of httpOnly.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
