import enum
import uuid
from datetime import time

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QueueType(str, enum.Enum):
    pre_ready = "pre_ready"
    main = "main"
    bar = "bar"


class MenuSection(Base):
    __tablename__ = "menu_sections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), index=True)
    name: Mapped[dict] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_sections.id"), index=True)
    name: Mapped[dict] = mapped_column(JSON)
    description: Mapped[dict] = mapped_column(JSON, default=dict)
    price: Mapped[float] = mapped_column(Float)
    picture_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False)
    diet_tags: Mapped[list[str]] = mapped_column(JSON, default=list)  # e.g. "kosher", "halal", "vegetarian", "gluten_free"
    allergens: Mapped[list[str]] = mapped_column(JSON, default=list)
    available_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    available_to: Mapped[time | None] = mapped_column(Time, nullable=True)
    queue_type: Mapped[QueueType] = mapped_column(Enum(QueueType), default=QueueType.main)
    customizations: Mapped[list] = mapped_column(JSON, default=list)
    supports_delayed_serve: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
