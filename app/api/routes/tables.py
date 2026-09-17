import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import get_db
from app.models.floor import Floor
from app.models.table import RestaurantTable
from app.models.user import User
from app.schemas.table import TableCreate, TableOut, TableUpdate

router = APIRouter(prefix="/restaurants/{slug}/tables", tags=["tables"])


async def _validate_floor(restaurant_id: uuid.UUID, floor_id: uuid.UUID | None, db: AsyncSession) -> None:
    if floor_id is None:
        return
    result = await db.execute(select(Floor).where(Floor.id == floor_id, Floor.restaurant_id == restaurant_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Floor not found for this restaurant")


@router.get("", response_model=list[TableOut])
async def list_tables(
    slug: str, floor_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[RestaurantTable]:
    restaurant = await get_restaurant_or_404(slug, db)
    query = select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant.id)
    if floor_id is not None:
        query = query.where(RestaurantTable.floor_id == floor_id)
    result = await db.execute(query.order_by(RestaurantTable.number))
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
    require_capability(restaurant, staff, "manage_tables")

    existing = await db.execute(
        select(RestaurantTable).where(
            RestaurantTable.restaurant_id == restaurant.id, RestaurantTable.number == payload.number
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Table number already exists")

    await _validate_floor(restaurant.id, payload.floor_id, db)

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
    require_capability(restaurant, staff, "manage_tables")

    result = await db.execute(
        select(RestaurantTable).where(RestaurantTable.id == table_id, RestaurantTable.restaurant_id == restaurant.id)
    )
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "floor_id" in update_data:
        await _validate_floor(restaurant.id, update_data["floor_id"], db)

    for field, value in update_data.items():
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
    require_capability(restaurant, staff, "manage_tables")

    result = await db.execute(
        select(RestaurantTable).where(RestaurantTable.id == table_id, RestaurantTable.restaurant_id == restaurant.id)
    )
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")

    await db.delete(table)
    await db.commit()
