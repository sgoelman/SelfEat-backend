import uuid

from pydantic import BaseModel, ConfigDict

from app.models.order import FulfillmentMode, OrderItemStatus, OrderStatus, PaymentMethod, PaymentStatus


class OrderItemCreate(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = 1
    customizations: dict = {}
    serve_after_food: bool = False
    serve_delay_minutes: int | None = None


class OrderCreate(BaseModel):
    table_id: uuid.UUID | None = None
    fulfillment_mode: FulfillmentMode = FulfillmentMode.when_ready
    payment_method: PaymentMethod | None = None
    tip_amount: float = 0
    items: list[OrderItemCreate]


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_item_id: uuid.UUID
    quantity: int
    unit_price: float
    customizations: dict
    status: OrderItemStatus
    assigned_staff_name: str | None
    serve_after_food: bool
    serve_delay_minutes: int | None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    table_id: uuid.UUID | None
    pickup_number: int | None
    status: OrderStatus
    fulfillment_mode: FulfillmentMode
    payment_method: PaymentMethod | None
    payment_status: PaymentStatus
    tip_amount: float
    total_amount: float
    items: list[OrderItemOut] = []


class ClaimRequest(BaseModel):
    staff_name: str


class KitchenQueueItemOut(OrderItemOut):
    """Kitchen/bar queue view — adds order context so staff know who to call or where to deliver."""

    order_id: uuid.UUID
    pickup_number: int | None
    table_number: int | None
    # Per-language dict, matching MenuItem.name — the WS broadcast in create_order already
    # includes this (menu_item_name), but the REST list this schema backs didn't, so a kitchen
    # screen that only loaded via GET (no live event yet) would see a queue of bare item IDs.
    menu_item_name: dict[str, str]
