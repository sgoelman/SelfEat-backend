import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.order import FulfillmentMode, OrderItemStatus, OrderStatus, PaymentMethod, PaymentStatus


class SelectedModifier(BaseModel):
    """What the diner picked for one modifier group — just ids, resolved server-side against the
    menu item's live ModifierGroup definitions (see _resolve_customizations in routes/orders.py)
    into the self-contained, denormalized snapshot that OrderItemOut.customizations returns."""

    group_id: str
    option_ids: list[str] = []


class OrderItemCreate(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = 1
    customizations: list[SelectedModifier] = []
    note: str | None = None
    serve_after_food: bool = False
    serve_delay_minutes: int | None = None


class SelectedModifierOut(BaseModel):
    """One resolved selection, denormalized at order-creation time (group/option names + price)
    so it stays accurate on the kitchen ticket even if the menu item's modifiers are edited or
    removed later — matches the existing menu_item_name denormalization pattern elsewhere here."""

    group_id: str
    group_name: dict[str, str]
    option_id: str
    label: dict[str, str]
    price_delta: float


class OrderCreate(BaseModel):
    table_id: uuid.UUID | None = None
    fulfillment_mode: FulfillmentMode = FulfillmentMode.when_ready
    payment_method: PaymentMethod | None = None
    tip_amount: float = 0
    items: list[OrderItemCreate]
    # Expo push token — set only if the diner granted notification permission client-side.
    # See app/services/push.py.
    push_token: str | None = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_item_id: uuid.UUID
    quantity: int
    unit_price: float
    customizations: list[SelectedModifierOut]
    note: str | None
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


class WaiterReadyItemOut(BaseModel):
    id: uuid.UUID
    menu_item_name: dict[str, str]
    quantity: int
    customizations: list[SelectedModifierOut]
    note: str | None
    ready_at: datetime


class WaiterDestinationOut(BaseModel):
    """One destination-first card, per UI/UX's design — a table or a pickup order, with every
    item that's ready for it grouped together, rather than one row per item."""

    table_number: int | None
    pickup_number: int | None
    items: list[WaiterReadyItemOut]
    oldest_ready_at: datetime  # drives the card's own urgency color — its longest-waiting item


class WaiterDisplayOut(BaseModel):
    destinations: list[WaiterDestinationOut]
    # Feeds UI/UX's collapsed, non-interactive "Still in the kitchen" line — situational
    # awareness without competing for the waiter's attention the way the ready list should.
    still_in_kitchen_count: int
