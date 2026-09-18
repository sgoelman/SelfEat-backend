import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    waiter = "waiter"
    kitchen = "kitchen"
    chef = "chef"
    customer = "customer"


STAFF_ROLES = {UserRole.owner, UserRole.manager, UserRole.waiter, UserRole.kitchen, UserRole.chef}


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
    # Set together for a diner who signed in via SSO (role=customer); both stay null for
    # staff/password accounts and for anonymous diners. provider_user_id is that provider's
    # own stable subject id — not email, since email can be unverified/absent/shared depending
    # on the provider and the diner's privacy choices (e.g. Apple's private relay addresses).
    auth_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "google" | "facebook" | "apple"
    provider_user_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
