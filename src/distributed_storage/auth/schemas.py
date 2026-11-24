import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _normalise_email(value: str) -> str:
    normalised = value.strip().lower()
    if not _EMAIL_PATTERN.fullmatch(normalised):
        raise ValueError("invalid email address")
    return normalised


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    auth_secret: str = Field(min_length=16, max_length=1024)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    auth_secret: str = Field(min_length=16, max_length=1024)
    device_name: str = Field(min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalise_email(value)

    @field_validator("device_name")
    @classmethod
    def _device_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("device name must not be blank")
        if any(ord(char) < 32 or ord(char) == 127 for char in stripped):
            raise ValueError("device name must not contain control characters")
        return stripped


class RegisterResponse(BaseModel):
    user_id: uuid.UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime
    device_id: uuid.UUID
