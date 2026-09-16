import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404
from app.core.database import get_db
from app.models.table import RestaurantTable
from app.models.user import User
from app.schemas.table import TableCreate, TableOut, TableUpdate

router = APIRouter(prefix="/restaurants/{slug}/tables", tags=["tables"])


@router.get("", response_model=list[TableOut])
async def list_tables(slug: str, db: AsyncSession = Depends(get_db)) -> list[RestaurantTable]:
    restaurant = await get_restaurant_or_404(slug, db)
    result = await db.execute(
        select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant.id).order_by(RestaurantTable.number)
    )
    return list(result.scalars().all())


@router.post("", response_model=TableOut, status_code=status.HTTP_201_CREATED)
async def create_table(
    slug: str,
    payload: TableCreate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> RestaurantTable:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)

    existing = await db.execute(
        select(RestaurantTable).where(
            RestaurantTable.restaurant_id == restaurant.id, RestaurantTable.number == payload.number
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Table number already exists")

    table = RestaurantTable(restaurant_id=restaurant.id, **payload.model_dump())
    db.add(table)
    await db.commit()
    await db.refresh(table)
    return table


@router.patch("/{table_id}", response_model=TableOut)
async def update_table(
    slug: str,
    table_id: uuid.UUID,
    payload: TableUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> RestaurantTable:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)

    result = await db.execute(
        select(RestaurantTable).where(RestaurantTable.id == table_id, RestaurantTable.restaurant_id == restaurant.id)
    )
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(table, field, value)

    await db.commit()
    await db.refresh(table)
    return table


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(
    slug: str,
    table_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> None:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)

    result = await db.execute(
        select(RestaurantTable).where(RestaurantTable.id == table_id, RestaurantTable.restaurant_id == restaurant.id)
    )
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")

    await db.delete(table)
    await db.commit()
