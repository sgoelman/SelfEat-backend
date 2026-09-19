import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_customer_optional, get_restaurant_or_404
from app.core.database import get_db
from app.models.menu import MenuItem, MenuSection
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut, SelectedModifier
from app.services.queue_manager import queue_manager

router = APIRouter(tags=["orders"])


def _resolve_customizations(menu_item: MenuItem, selections: list[SelectedModifier]) -> tuple[list[dict], float]:
    """Validates the diner's picks against the menu item's live ModifierGroup definitions and
    resolves them into a self-contained, denormalized snapshot (see SelectedModifierOut) — the
    kitchen ticket then just renders it directly, with no second lookup and no risk of drifting
    if the menu item's modifiers are edited or removed after this order was placed.

    Raises 400 on anything that violates a group's required/cardinality rule, or references a
    group/option that doesn't exist on this item — a diner-facing validation error, not a bug.
    """
    groups: list[dict] = menu_item.customizations
    groups_by_id = {g["id"]: g for g in groups}
    selections_by_group = {s.group_id: s.option_ids for s in selections}

    unknown_groups = set(selections_by_group) - set(groups_by_id)
    if unknown_groups:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown modifier group(s): {', '.join(sorted(unknown_groups))}")

    resolved: list[dict] = []
    price_delta_total = 0.0
    for group in groups:
        option_ids = selections_by_group.get(group["id"], [])
        selection_type = group["selection_type"]
        required_min = 1 if selection_type == "single_required" else group.get("min_select", 0)
        max_select = 1 if selection_type in ("single_required", "single_optional") else group.get("max_select")

        if len(option_ids) < required_min:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{group['id']}' requires at least {required_min} selection(s)")
        if max_select is not None and len(option_ids) > max_select:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{group['id']}' allows at most {max_select} selection(s)")

        options_by_id = {o["id"]: o for o in group["options"]}
        for option_id in option_ids:
            option = options_by_id.get(option_id)
            if option is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Option '{option_id}' is not valid for group '{group['id']}'")
            resolved.append(
                {
                    "group_id": group["id"],
                    "group_name": group["name"],
                    "option_id": option_id,
                    "label": option["label"],
                    "price_delta": option.get("price_delta", 0),
                }
            )
            price_delta_total += option.get("price_delta", 0)

    return resolved, price_delta_total


async def _next_pickup_number(restaurant_id: uuid.UUID, db: AsyncSession) -> int:
    """Per-restaurant sequential number for table-less orders, reset daily (UTC).

    Counts today's orders + 1 rather than using a DB sequence — simple and good enough at
    small-kiosk volume; not race-proof under heavy concurrent load.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count()).select_from(Order).where(Order.restaurant_id == restaurant_id, Order.created_at >= today_start)
    )
    return (result.scalar_one() or 0) + 1


@router.post("/restaurants/{slug}/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    slug: str,
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    customer: User | None = Depends(get_current_customer_optional),
) -> Order:
    restaurant = await get_restaurant_or_404(slug, db)

    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order must contain at least one item")

    pickup_number = None if payload.table_id else await _next_pickup_number(restaurant.id, db)

    order = Order(
        restaurant_id=restaurant.id,
        table_id=payload.table_id,
        customer_id=customer.id if customer else None,
        pickup_number=pickup_number,
        fulfillment_mode=payload.fulfillment_mode,
        payment_method=payload.payment_method,
        tip_amount=payload.tip_amount,
        push_token=payload.push_token,
    )
    db.add(order)
    await db.flush()

    total = payload.tip_amount
    order_items: list[OrderItem] = []
    for line in payload.items:
        # Joined through MenuSection so an item from a different restaurant can't be priced
        # into this order — menu_item_id alone isn't restaurant-scoped.
        menu_item_result = await db.execute(
            select(MenuItem)
            .join(MenuSection, MenuItem.section_id == MenuSection.id)
            .where(MenuItem.id == line.menu_item_id, MenuSection.restaurant_id == restaurant.id)
        )
        menu_item = menu_item_result.scalar_one_or_none()
        if menu_item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Menu item {line.menu_item_id} not found")

        resolved_customizations, price_delta = _resolve_customizations(menu_item, line.customizations)
        unit_price = menu_item.price + price_delta
        total += unit_price * line.quantity

        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            quantity=line.quantity,
            unit_price=unit_price,
            customizations=resolved_customizations,
            note=line.note,
            serve_after_food=line.serve_after_food,
            serve_delay_minutes=line.serve_delay_minutes,
        )
        db.add(order_item)
        order_items.append(order_item)

    order.total_amount = total
    await db.commit()
    await db.refresh(order)

    for item in order_items:
        await db.refresh(item)
        menu_item_result = await db.execute(select(MenuItem).where(MenuItem.id == item.menu_item_id))
        menu_item = menu_item_result.scalar_one()
        await queue_manager.broadcast(
            restaurant.id,
            menu_item.queue_type.value,
            {
                "event": "item_queued",
                "order_item_id": str(item.id),
                "order_id": str(order.id),
                "pickup_number": order.pickup_number,
                "menu_item_name": menu_item.name,
                "quantity": item.quantity,
                "customizations": item.customizations,
                "note": item.note,
            },
        )

    order.items = order_items
    return order


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Order:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    order.items = items_result.scalars().all()
    return order
