import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import get_db
from app.models.floor import Floor
from app.models.table import RestaurantTable
from app.models.user import User
from app.schemas.floor import FloorCreate, FloorOut, FloorUpdate

router = APIRouter(prefix="/restaurants/{slug}/floors", tags=["floors"])


@router.get("", response_model=list[FloorOut])
async def list_floors(slug: str, db: AsyncSession = Depends(get_db)) -> list[Floor]:
    restaurant = await get_restaurant_or_404(slug, db)
    result = await db.execute(select(Floor).where(Floor.restaurant_id == restaurant.id).order_by(Floor.sort_order))
    return list(result.scalars().all())


@router.post("", response_model=FloorOut, status_code=status.HTTP_201_CREATED)
async def create_floor(
    slug: str,
    payload: FloorCreate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> Floor:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_tables")

    existing = await db.execute(
        select(Floor).where(Floor.restaurant_id == restaurant.id, Floor.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A floor with this name already exists")

    floor = Floor(restaurant_id=restaurant.id, **payload.model_dump())
    db.add(floor)
    await db.commit()
    await db.refresh(floor)
    return floor


@router.patch("/{floor_id}", response_model=FloorOut)
async def update_floor(
    slug: str,
    floor_id: uuid.UUID,
    payload: FloorUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> Floor:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_tables")

    result = await db.execute(select(Floor).where(Floor.id == floor_id, Floor.restaurant_id == restaurant.id))
    floor = result.scalar_one_or_none()
    if floor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Floor not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(floor, field, value)

    await db.commit()
    await db.refresh(floor)
    return floor


@router.delete("/{floor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_floor(
    slug: str,
    floor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> None:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_tables")

    result = await db.execute(select(Floor).where(Floor.id == floor_id, Floor.restaurant_id == restaurant.id))
    floor = result.scalar_one_or_none()
    if floor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Floor not found")

    # Tables on this floor are not deleted — they fall back to "no floor" (floor_id NULL) rather
    # than disappearing, since losing a table's QR code / configured menu links would be worse.
    tables_result = await db.execute(select(RestaurantTable).where(RestaurantTable.floor_id == floor.id))
    for table in tables_result.scalars().all():
        table.floor_id = None

    await db.delete(floor)
    await db.commit()
