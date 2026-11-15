import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    # в базу кладём уже приведённый к нижнему регистру email, это делает AuthService
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(
        String(10), default=UserRole.USER.value, server_default=UserRole.USER.value
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
