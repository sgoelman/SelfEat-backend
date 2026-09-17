from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_restaurant_or_404
from app.core.database import get_db
from app.core.security import hash_password
from app.models.menu import MenuItem, MenuSection
from app.models.restaurant import Restaurant
from app.models.table import RestaurantTable
from app.models.user import User, UserRole
from app.schemas.menu import MenuItemOut, MenuSectionWithItems
from app.schemas.restaurant import RestaurantCreate, RestaurantPublic
from app.schemas.table import QrResolveOut

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("/qr/{qr_token}", response_model=QrResolveOut)
async def resolve_qr_token(qr_token: str, db: AsyncSession = Depends(get_db)) -> QrResolveOut:
    """Bootstrap call for the diner app: turns a scanned table QR code into a restaurant + table.

    Counter/pickup QR codes (kiosk mode) don't go through this — they encode the restaurant slug
    directly (see SettingsScreen's counter QR) since there's no table to resolve.
    """
    result = await db.execute(
        select(RestaurantTable, Restaurant)
        .join(Restaurant, RestaurantTable.restaurant_id == Restaurant.id)
        .where(RestaurantTable.qr_token == qr_token)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unrecognized QR code")
    table, restaurant = row

    return QrResolveOut(
        restaurant_slug=restaurant.slug,
        restaurant_name=restaurant.name,
        table_id=table.id,
        table_number=table.number,
    )


@router.post("", response_model=RestaurantPublic, status_code=status.HTTP_201_CREATED)
async def create_restaurant(payload: RestaurantCreate, db: AsyncSession = Depends(get_db)) -> Restaurant:
    existing = await db.execute(select(Restaurant).where(Restaurant.slug == payload.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already taken")

    restaurant = Restaurant(slug=payload.slug, name=payload.name, languages=payload.languages)
    db.add(restaurant)
    await db.flush()

    owner = User(
        restaurant_id=restaurant.id,
        role=UserRole.owner,
        email=payload.owner_email,
        hashed_password=hash_password(payload.owner_password),
    )
    db.add(owner)
    await db.commit()
    await db.refresh(restaurant)
    return restaurant


@router.get("/{slug}", response_model=RestaurantPublic)
async def get_restaurant(slug: str, db: AsyncSession = Depends(get_db)) -> Restaurant:
    return await get_restaurant_or_404(slug, db)


@router.get("/{slug}/menu", response_model=list[MenuSectionWithItems])
async def get_menu(slug: str, db: AsyncSession = Depends(get_db)) -> list[MenuSectionWithItems]:
    restaurant = await get_restaurant_or_404(slug, db)

    sections_result = await db.execute(
        select(MenuSection).where(MenuSection.restaurant_id == restaurant.id).order_by(MenuSection.sort_order)
    )
    sections = sections_result.scalars().all()

    now = datetime.now(timezone.utc).time()
    out: list[MenuSectionWithItems] = []
    for section in sections:
        items_result = await db.execute(
            select(MenuItem).where(MenuItem.section_id == section.id).order_by(MenuItem.sort_order)
        )
        items = [
            item
            for item in items_result.scalars().all()
            if (item.available_from is None or item.available_from <= now)
            and (item.available_to is None or now <= item.available_to)
        ]
        section_out = MenuSectionWithItems.model_validate(section)
        section_out.items = [MenuItemOut.model_validate(item) for item in items]
        out.append(section_out)

    return out
