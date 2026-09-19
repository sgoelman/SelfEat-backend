import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.config import settings
from app.core.database import get_db
from app.models.menu import MenuItem, MenuSection
from app.models.menu_extraction import MenuExtractionUsage
from app.models.user import User
from app.schemas.menu import (
    ExtractedMenuItemOut,
    MenuExtractionResultOut,
    MenuItemCreate,
    MenuItemOut,
    MenuItemUpdate,
    MenuSectionCreate,
    MenuSectionOut,
    MenuSectionUpdate,
    MenuSectionWithItems,
)
from app.services.menu_extraction import MenuExtractionError, extract_menu_items_from_image

router = APIRouter(prefix="/restaurants/{slug}", tags=["menu-admin"])

MAX_MENU_PHOTO_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_MENU_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


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


@router.post("/menu/extract", response_model=MenuExtractionResultOut)
async def extract_menu_from_photo(
    slug: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> MenuExtractionResultOut:
    """Pro-tier only: AI-assisted menu entry from a photo of a menu (Gemini 2.5 Flash via Vertex
    AI). Returns candidate items for the restaurant to review/edit client-side — never creates
    MenuItem rows directly, since text extraction is reliable but not guaranteed-correct (see
    TASKS.md; auto-cropping individual dish photos is explicitly descoped, item photos stay a
    manual per-item upload)."""
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_menu")

    if restaurant.plan != "pro":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "AI menu upload is a Pro-tier feature")

    if file.content_type not in ALLOWED_MENU_PHOTO_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a JPEG, PNG, or WEBP image")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_MENU_PHOTO_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image too large (10MB max)")

    # Real spend backstop (TASKS.md: "needs a usage-tracking backstop, not just a GCP budget
    # alert") — a company-wide monthly call cap, incremented before the Vertex AI call since
    # Google bills on the request itself, not on whether we can parse what comes back.
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    usage_result = await db.execute(select(MenuExtractionUsage).where(MenuExtractionUsage.year_month == year_month))
    usage = usage_result.scalar_one_or_none()
    if usage is None:
        usage = MenuExtractionUsage(year_month=year_month, call_count=0)
        db.add(usage)
        await db.flush()

    if usage.call_count >= settings.menu_extraction_monthly_call_cap:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Monthly AI menu-extraction budget reached — try again next month or add items manually",
        )

    usage.call_count += 1
    await db.commit()

    try:
        extracted = await extract_menu_items_from_image(image_bytes, file.content_type)
    except MenuExtractionError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return MenuExtractionResultOut(items=[ExtractedMenuItemOut(**item.model_dump()) for item in extracted])
