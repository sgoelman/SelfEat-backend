import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.permissions import default_role_permissions
from app.models.base import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    bank_details: Mapped[dict] = mapped_column(JSON, default=dict)
    role_permissions: Mapped[dict] = mapped_column(JSON, default=default_role_permissions)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # "free" | "pro" — gates Pro-only features like AI menu upload
    # The free item offered to a customer for signing up instead of staying anonymous (business model: restaurant
    # funds this gift, Self-Eat charges the restaurant per acquired signup). Redemption itself lives in the diner
    # app, which doesn't exist yet — this is just the restaurant's choice of which item to offer.
    signup_gift_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("menu_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
