import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import AsyncSessionLocal, get_db
from app.models.menu import MenuItem, QueueType
from app.models.order import Order, OrderItem, OrderItemStatus
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.order import ClaimRequest, OrderItemOut
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


@router.get("/restaurants/{slug}/kitchen/{queue_type}", response_model=list[OrderItemOut])
async def list_queue(
    slug: str,
    queue_type: QueueType,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> list[OrderItem]:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "view_kitchen_queue")

    result = await db.execute(
        select(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .join(MenuItem, OrderItem.menu_item_id == MenuItem.id)
        .where(
            Order.restaurant_id == restaurant.id,
            MenuItem.queue_type == queue_type,
            OrderItem.status.in_([OrderItemStatus.queued, OrderItemStatus.in_progress]),
        )
    )
    return list(result.scalars().all())


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
    await db.commit()
    await db.refresh(order_item)

    await queue_manager.broadcast(
        order.restaurant_id,
        menu_item.queue_type.value,
        {"event": "item_ready", "order_item_id": str(order_item.id), "order_id": str(order.id)},
    )
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
