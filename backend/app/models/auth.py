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
    nickname: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UserPublic(BaseModel):
    username: str
    role: UserRole
    nickname: str | None = None
    avatar_url: str | None = None
    is_active: bool = True


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=512)


class UserProfileUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=32)
    nickname: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=512)


class PasswordUpdateRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class AdminPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminUserUpdateRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class UserListResponse(BaseModel):
    items: list[UserPublic]


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: UserPublic


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthMeResponse(BaseModel):
    user: UserPublic


class RegistrationSettingsResponse(BaseModel):
    enabled: bool


class RegistrationSettingsUpdateRequest(BaseModel):
    enabled: bool
