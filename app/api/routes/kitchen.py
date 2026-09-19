import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import AsyncSessionLocal, get_db
from app.models.menu import MenuItem, QueueType
from app.models.order import FulfillmentMode, Order, OrderItem, OrderItemStatus
from app.models.restaurant import Restaurant
from app.models.table import RestaurantTable
from app.models.user import User
from app.schemas.order import ClaimRequest, KitchenQueueItemOut, OrderItemOut
from app.services.push import send_push
from app.services.queue_manager import queue_manager

router = APIRouter(tags=["kitchen"])


async def _load_item_with_context(item_id: uuid.UUID, db: AsyncSession) -> tuple[OrderItem, Order, MenuItem]:
    result = await db.execute(
        select(OrderItem, Order, MenuItem)
        .join(Order, OrderItem.order_id == Order.id)
        .join(MenuItem, OrderItem.menu_item_id == MenuItem.id)
        .where(OrderItem.id == item_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order item not found")
    return row[0], row[1], row[2]


@router.get("/restaurants/{slug}/kitchen/{queue_type}", response_model=list[KitchenQueueItemOut])
async def list_queue(
    slug: str,
    queue_type: QueueType,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> list[KitchenQueueItemOut]:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "view_kitchen_queue")

    result = await db.execute(
        select(OrderItem, Order, RestaurantTable, MenuItem)
        .join(Order, OrderItem.order_id == Order.id)
        .join(MenuItem, OrderItem.menu_item_id == MenuItem.id)
        .outerjoin(RestaurantTable, Order.table_id == RestaurantTable.id)
        .where(
            Order.restaurant_id == restaurant.id,
            MenuItem.queue_type == queue_type,
            OrderItem.status.in_([OrderItemStatus.queued, OrderItemStatus.in_progress]),
        )
        # True FIFO — first order placed is first shown, regardless of item/table.
        .order_by(OrderItem.created_at)
    )
    out: list[KitchenQueueItemOut] = []
    for order_item, order, table, menu_item in result.all():
        base = OrderItemOut.model_validate(order_item).model_dump()
        out.append(
            KitchenQueueItemOut(
                **base,
                order_id=order.id,
                pickup_number=order.pickup_number,
                table_number=table.number if table else None,
                menu_item_name=menu_item.name,
            )
        )
    return out


@router.post("/order-items/{item_id}/claim", response_model=OrderItemOut)
async def claim_item(
    item_id: uuid.UUID,
    payload: ClaimRequest,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> OrderItem:
    order_item, order, menu_item = await _load_item_with_context(item_id, db)
    if staff.restaurant_id != order.restaurant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this restaurant")
    restaurant = await db.get(Restaurant, order.restaurant_id)
    require_capability(restaurant, staff, "claim_kitchen_items")

    order_item.status = OrderItemStatus.in_progress
    order_item.assigned_staff_name = payload.staff_name
    await db.commit()
    await db.refresh(order_item)

    await queue_manager.broadcast(
        order.restaurant_id,
        menu_item.queue_type.value,
        {"event": "item_claimed", "order_item_id": str(order_item.id), "staff_name": payload.staff_name},
    )
    return order_item


async def _maybe_send_ready_push(order: Order, ready_item: OrderItem, menu_item: MenuItem, db: AsyncSession) -> None:
    """Replaces restaurant buzzer pagers with a real OS push — see services/push.py.

    "when_ready" fulfillment (items delivered to the table as each finishes) notifies per item,
    matching that mode's whole premise. "all_together" (the kitchen holds everything for one
    delivery) would make a push per item misleading — the diner isn't getting anything yet — so
    it waits and sends exactly one push, when the last item still outstanding goes ready.
    """
    if not order.push_token:
        return

    item_name = menu_item.name.get("en") or next(iter(menu_item.name.values()), "Item")

    if order.fulfillment_mode == FulfillmentMode.when_ready:
        await send_push(
            order.push_token,
            "Your food is ready!",
            f"{item_name} is ready.",
            {"order_id": str(order.id), "order_item_id": str(ready_item.id)},
        )
        return

    # all_together — only notify once every item has reached ready or delivered.
    other_items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    all_items = other_items_result.scalars().all()
    if all(i.status in (OrderItemStatus.ready, OrderItemStatus.delivered) for i in all_items):
        await send_push(
            order.push_token,
            "Your order is ready!",
            "Everything's ready — enjoy your meal.",
            {"order_id": str(order.id)},
        )


@router.post("/order-items/{item_id}/ready", response_model=OrderItemOut)
async def mark_ready(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> OrderItem:
    order_item, order, menu_item = await _load_item_with_context(item_id, db)
    if staff.restaurant_id != order.restaurant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this restaurant")
    restaurant = await db.get(Restaurant, order.restaurant_id)
    require_capability(restaurant, staff, "claim_kitchen_items")

    order_item.status = OrderItemStatus.ready
    order_item.ready_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order_item)

    await queue_manager.broadcast(
        order.restaurant_id,
        menu_item.queue_type.value,
        {"event": "item_ready", "order_item_id": str(order_item.id), "order_id": str(order.id)},
    )
    await _maybe_send_ready_push(order, order_item, menu_item, db)
    return order_item


@router.websocket("/ws/kitchen/{slug}/{queue_type}")
async def kitchen_feed(websocket: WebSocket, slug: str, queue_type: QueueType) -> None:
    async with AsyncSessionLocal() as db:
        restaurant = await get_restaurant_or_404(slug, db)

    await queue_manager.connect(websocket, restaurant.id, queue_type.value)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        queue_manager.disconnect(websocket, restaurant.id, queue_type.value)
