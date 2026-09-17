from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import get_db
from app.core.permissions import CAPABILITIES
from app.core.security import hash_password
from app.models.menu import MenuItem, MenuSection
from app.models.restaurant import Restaurant
from app.models.user import User, UserRole
from app.schemas.settings import (
    RolePermissionsOut,
    RolePermissionsUpdate,
    SignupGiftOut,
    SignupGiftUpdate,
    StaffCreate,
    StaffOut,
)

router = APIRouter(prefix="/restaurants/{slug}", tags=["settings"])


@router.get("/settings/roles", response_model=RolePermissionsOut)
async def get_role_permissions(
    slug: str,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> RolePermissionsOut:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_settings")

    return RolePermissionsOut(
        permissions=restaurant.role_permissions,
        capabilities=CAPABILITIES,
        roles=[r.value for r in UserRole if r != UserRole.customer],
    )


@router.put("/settings/roles", response_model=RolePermissionsOut)
async def update_role_permissions(
    slug: str,
    payload: RolePermissionsUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> RolePermissionsOut:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_settings")

    cleaned: dict[str, list[str]] = {}
    for role, caps in payload.permissions.items():
        cleaned[role] = [c for c in caps if c in CAPABILITIES]

    # Owner always keeps every capability — prevents accidentally locking the account out.
    cleaned[UserRole.owner.value] = list(CAPABILITIES)

    restaurant.role_permissions = cleaned
    await db.commit()
    await db.refresh(restaurant)

    return RolePermissionsOut(
        permissions=restaurant.role_permissions,
        capabilities=CAPABILITIES,
        roles=[r.value for r in UserRole if r != UserRole.customer],
    )


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(
    slug: str,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> list[User]:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_staff")

    result = await db.execute(select(User).where(User.restaurant_id == restaurant.id))
    return list(result.scalars().all())


@router.post("/staff", response_model=StaffOut, status_code=201)
async def create_staff(
    slug: str,
    payload: StaffCreate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> User:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_staff")

    new_staff = User(
        restaurant_id=restaurant.id,
        role=payload.role,
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    db.add(new_staff)
    await db.commit()
    await db.refresh(new_staff)
    return new_staff


@router.put("/settings/gift", response_model=SignupGiftOut)
async def update_signup_gift(
    slug: str,
    payload: SignupGiftUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> SignupGiftOut:
    """The item offered free to a customer for signing up instead of staying anonymous.

    Redemption/verification lives in the diner app (not built yet) — this just lets the
    restaurant choose which of their own menu items to offer.
    """
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_settings")

    if payload.menu_item_id is not None:
        owned_result = await db.execute(
            select(MenuItem)
            .join(MenuSection, MenuItem.section_id == MenuSection.id)
            .where(MenuItem.id == payload.menu_item_id, MenuSection.restaurant_id == restaurant.id)
        )
        if owned_result.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found for this restaurant")

    restaurant.signup_gift_item_id = payload.menu_item_id
    await db.commit()
    await db.refresh(restaurant)
    return SignupGiftOut(menu_item_id=restaurant.signup_gift_item_id)
