import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrderStatus(str, enum.Enum):
    open = "open"
    paid = "paid"
    completed = "completed"
    cancelled = "cancelled"


class FulfillmentMode(str, enum.Enum):
    when_ready = "when_ready"
    all_together = "all_together"


class PaymentMethod(str, enum.Enum):
    paypal = "paypal"
    card = "card"
    google_pay = "google_pay"
    apple_pay = "apple_pay"
    local_epay = "local_epay"
    pay_on_pickup = "pay_on_pickup"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), index=True)
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("restaurant_tables.id"), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.open)
    fulfillment_mode: Mapped[FulfillmentMode] = mapped_column(Enum(FulfillmentMode), default=FulfillmentMode.when_ready)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(Enum(PaymentMethod), nullable=True)
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.pending)
    tip_amount: Mapped[float] = mapped_column(Float, default=0)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    # Per-restaurant sequential number for table-less (kiosk/counter) orders — lets staff call
    # "Order #12" instead of a table number. Set at creation; see create_order in routes/orders.py.
    pickup_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class OrderItemStatus(str, enum.Enum):
    queued = "queued"
    in_progress = "in_progress"
    ready = "ready"
    delivered = "delivered"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float)
    customizations: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[OrderItemStatus] = mapped_column(Enum(OrderItemStatus), default=OrderItemStatus.queued, index=True)
    assigned_staff_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serve_after_food: Mapped[bool] = mapped_column(Boolean, default=False)
    serve_delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    # When this item transitioned into ready/delivered — the Waiter Display's urgency coloring is
    # based on elapsed time since ready_at (how long has this been sitting, waiting for a waiter),
    # which created_at can't answer since that's order-placement time, not prep-completion time.
    ready_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
