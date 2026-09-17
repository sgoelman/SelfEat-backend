import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import get_db
from app.models.menu import MenuItem, MenuSection
from app.models.user import User
from app.schemas.menu import (
    MenuItemCreate,
    MenuItemOut,
    MenuItemUpdate,
    MenuSectionCreate,
    MenuSectionOut,
    MenuSectionUpdate,
    MenuSectionWithItems,
)

router = APIRouter(prefix="/restaurants/{slug}", tags=["menu-admin"])


@router.get("/sections", response_model=list[MenuSectionWithItems])
async def list_sections_admin(
    slug: str,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> list[MenuSectionWithItems]:
    """Unfiltered admin view — unlike the public /menu endpoint, this ignores item availability windows."""
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    sections_result = await db.execute(
        select(MenuSection).where(MenuSection.restaurant_id == restaurant.id).order_by(MenuSection.sort_order)
    )
    sections = sections_result.scalars().all()

    out: list[MenuSectionWithItems] = []
    for section in sections:
        items_result = await db.execute(
            select(MenuItem).where(MenuItem.section_id == section.id).order_by(MenuItem.sort_order)
        )
        section_out = MenuSectionWithItems.model_validate(section)
        section_out.items = [MenuItemOut.model_validate(item) for item in items_result.scalars().all()]
        out.append(section_out)

    return out


@router.post("/sections", response_model=MenuSectionOut, status_code=status.HTTP_201_CREATED)
async def create_section(
    slug: str,
    payload: MenuSectionCreate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> MenuSection:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    section = MenuSection(restaurant_id=restaurant.id, **payload.model_dump())
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


@router.patch("/sections/{section_id}", response_model=MenuSectionOut)
async def update_section(
    slug: str,
    section_id: uuid.UUID,
    payload: MenuSectionUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> MenuSection:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    result = await db.execute(
        select(MenuSection).where(MenuSection.id == section_id, MenuSection.restaurant_id == restaurant.id)
    )
    section = result.scalar_one_or_none()
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(section, field, value)

    await db.commit()
    await db.refresh(section)
    return section


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    slug: str,
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> None:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    result = await db.execute(
        select(MenuSection).where(MenuSection.id == section_id, MenuSection.restaurant_id == restaurant.id)
    )
    section = result.scalar_one_or_none()
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")

    items_result = await db.execute(select(MenuItem).where(MenuItem.section_id == section.id))
    for item in items_result.scalars().all():
        await db.delete(item)

    await db.delete(section)
    await db.commit()


@router.post("/items", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    slug: str,
    payload: MenuItemCreate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> MenuItem:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    section_result = await db.execute(
        select(MenuSection).where(MenuSection.id == payload.section_id, MenuSection.restaurant_id == restaurant.id)
    )
    if section_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")

    item = MenuItem(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=MenuItemOut)
async def update_item(
    slug: str,
    item_id: uuid.UUID,
    payload: MenuItemUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> MenuItem:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    result = await db.execute(
        select(MenuItem)
        .join(MenuSection, MenuItem.section_id == MenuSection.id)
        .where(MenuItem.id == item_id, MenuSection.restaurant_id == restaurant.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    slug: str,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> None:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    result = await db.execute(
        select(MenuItem)
        .join(MenuSection, MenuItem.section_id == MenuSection.id)
        .where(MenuItem.id == item_id, MenuSection.restaurant_id == restaurant.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    await db.delete(item)
    await db.commit()
