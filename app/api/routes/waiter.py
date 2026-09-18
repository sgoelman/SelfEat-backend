import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import get_db
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, OrderItemStatus
from app.models.restaurant import Restaurant
from app.models.table import RestaurantTable
from app.models.user import User
from app.schemas.order import OrderItemOut, WaiterDestinationOut, WaiterDisplayOut, WaiterReadyItemOut

router = APIRouter(tags=["waiter"])


@router.get("/restaurants/{slug}/waiter/display", response_model=WaiterDisplayOut)
async def get_waiter_display(
    slug: str,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> WaiterDisplayOut:
    """Destination-first, per UI/UX's design — a waiter cares "who's waiting on something right
    now," not which kitchen station made it, so this groups ready items by table/pickup rather
    than listing them per-item the way the kitchen board does."""
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "deliver_orders")

    # coalesce to created_at: an item already `ready` from before ready_at existed (e.g. at the
    # moment this migration deploys, for any restaurant with orders already in flight) would
    # otherwise have a NULL ready_at and crash this endpoint outright — created_at is an
    # imperfect but safe, non-crashing stand-in for those legacy rows.
    effective_ready_at = func.coalesce(OrderItem.ready_at, OrderItem.created_at)

    ready_result = await db.execute(
        select(OrderItem, Order, RestaurantTable, MenuItem, effective_ready_at)
        .join(Order, OrderItem.order_id == Order.id)
        .join(MenuItem, OrderItem.menu_item_id == MenuItem.id)
        .outerjoin(RestaurantTable, Order.table_id == RestaurantTable.id)
        .where(Order.restaurant_id == restaurant.id, OrderItem.status == OrderItemStatus.ready)
        .order_by(effective_ready_at)
    )

    # Grouped in Python, not SQL — same "fine at small-kiosk/restaurant volume, not built for
    # heavy concurrent scale" tradeoff already made elsewhere in this codebase (see
    # _next_pickup_number in routes/orders.py).
    destinations: dict[tuple[int | None, int | None], WaiterDestinationOut] = {}
    for order_item, order, table, menu_item, ready_at in ready_result.all():
        key = (table.number if table else None, order.pickup_number)
        item_out = WaiterReadyItemOut(id=order_item.id, menu_item_name=menu_item.name, quantity=order_item.quantity, ready_at=ready_at)
        if key not in destinations:
            destinations[key] = WaiterDestinationOut(
                table_number=key[0], pickup_number=key[1], items=[item_out], oldest_ready_at=ready_at
            )
        else:
            destinations[key].items.append(item_out)
            # ready_at ascending order from the query means the first item seen per destination
            # is already its oldest — oldest_ready_at doesn't need updating on later items.

    still_cooking_result = await db.execute(
        select(func.count())
        .select_from(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.restaurant_id == restaurant.id, OrderItem.status.in_([OrderItemStatus.queued, OrderItemStatus.in_progress]))
    )

    return WaiterDisplayOut(
        # Oldest-ready-first overall — the most urgent card leads, matching the single
        # urgency-sorted list UI/UX specified rather than grouping by table number.
        destinations=sorted(destinations.values(), key=lambda d: d.oldest_ready_at),
        still_in_kitchen_count=still_cooking_result.scalar_one() or 0,
    )


@router.post("/order-items/{item_id}/delivered", response_model=OrderItemOut)
async def mark_delivered(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> OrderItem:
    result = await db.execute(select(OrderItem, Order).join(Order, OrderItem.order_id == Order.id).where(OrderItem.id == item_id))
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order item not found")
    order_item, order = row

    if staff.restaurant_id != order.restaurant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this restaurant")
    restaurant = await db.get(Restaurant, order.restaurant_id)
    require_capability(restaurant, staff, "deliver_orders")

    if order_item.status != OrderItemStatus.ready:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a ready item can be marked delivered")

    order_item.status = OrderItemStatus.delivered
    order_item.delivered_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order_item)
    return order_item
