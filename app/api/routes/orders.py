import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_restaurant_or_404
from app.core.database import get_db
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderOut
from app.services.queue_manager import queue_manager

router = APIRouter(tags=["orders"])


@router.post("/restaurants/{slug}/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(slug: str, payload: OrderCreate, db: AsyncSession = Depends(get_db)) -> Order:
    restaurant = await get_restaurant_or_404(slug, db)

    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order must contain at least one item")

    order = Order(
        restaurant_id=restaurant.id,
        table_id=payload.table_id,
        fulfillment_mode=payload.fulfillment_mode,
        payment_method=payload.payment_method,
        tip_amount=payload.tip_amount,
    )
    db.add(order)
    await db.flush()

    total = payload.tip_amount
    order_items: list[OrderItem] = []
    for line in payload.items:
        menu_item_result = await db.execute(select(MenuItem).where(MenuItem.id == line.menu_item_id))
        menu_item = menu_item_result.scalar_one_or_none()
        if menu_item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Menu item {line.menu_item_id} not found")

        unit_price = menu_item.price
        total += unit_price * line.quantity

        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            quantity=line.quantity,
            unit_price=unit_price,
            customizations=line.customizations,
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
                "menu_item_name": menu_item.name,
                "quantity": item.quantity,
                "customizations": item.customizations,
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
