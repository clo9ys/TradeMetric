import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator

from app.domain.enums import UserRole


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def has_changes(self) -> Self:
        if self.role is None and self.is_active is None:
            raise ValueError("Укажите role или is_active")
        return self


class PasswordChange(BaseModel):
    password: SecretStr = Field(min_length=8, max_length=128)
