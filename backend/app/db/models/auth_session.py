import uuid
from datetime import datetime

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.user import User


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (CheckConstraint("expires_at > created_at", name="expires_after_created"),)

    # в cookie лежит сам токен, в базе только его SHA-256 (64 hex-символа)
    token_hash: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # lazy="raise": в async неявная подгрузка невозможна, грузим явно через options()
    user: Mapped[User] = relationship(lazy="raise")
