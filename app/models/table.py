import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"
    __table_args__ = (UniqueConstraint("restaurant_id", "number", name="uq_table_number_per_restaurant"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    shape: Mapped[str] = mapped_column(String(20), default="round")
    color: Mapped[str] = mapped_column(String(20), default="#c8a15a")
    pos_x: Mapped[float] = mapped_column(Float, default=0)
    pos_y: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[float] = mapped_column(Float, default=80)
    height: Mapped[float] = mapped_column(Float, default=80)
    qr_token: Mapped[str] = mapped_column(String(40), unique=True, index=True, default=lambda: uuid.uuid4().hex)
