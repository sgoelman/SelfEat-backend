import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRole(str, enum.Enum):
    owner = "owner"
    staff = "staff"
    customer = "customer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("restaurants.id"), nullable=True, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
