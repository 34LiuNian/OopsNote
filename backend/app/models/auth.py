from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "member"]


class UserRecord(BaseModel):
    username: str
    password_hash: str
    role: UserRole = "member"
    is_active: bool = True
    created_at: datetime


class UserPublic(BaseModel):
    username: str
    role: UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class AuthMeResponse(BaseModel):
    user: UserPublic
