import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Floor(Base):
    __tablename__ = "floors"
    __table_args__ = (UniqueConstraint("restaurant_id", "name", name="uq_floor_name_per_restaurant"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
