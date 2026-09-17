import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_staff_belongs, get_current_staff, get_restaurant_or_404, require_capability
from app.core.database import get_db
from app.core.permissions import CAPABILITIES
from app.core.security import hash_password
from app.models.menu import MenuItem, MenuSection
from app.models.order import Order, OrderStatus
from app.models.restaurant import Restaurant
from app.models.user import User, UserRole
from app.schemas.settings import (
    RolePermissionsOut,
    RolePermissionsUpdate,
    SignupGiftOut,
    SignupGiftUpdate,
    StaffCreate,
    StaffOut,
    StaffUpdate,
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

    if payload.role == UserRole.owner:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot create a staff member with the owner role.")

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


@router.patch("/staff/{staff_id}", response_model=StaffOut)
async def update_staff(
    slug: str,
    staff_id: uuid.UUID,
    payload: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> User:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_staff")

    result = await db.execute(select(User).where(User.id == staff_id, User.restaurant_id == restaurant.id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")

    if target.role == UserRole.owner or payload.role == UserRole.owner:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change the owner's role, or grant the owner role, via this endpoint.")

    target.role = payload.role
    await db.commit()
    await db.refresh(target)
    return target


# Below this average order value, a % discount on the next order costs the restaurant less
# per redemption than a free item — see SignupGiftOut.discount_suggested.
DISCOUNT_SUGGESTED_THRESHOLD = 15.0


async def _average_order_value(restaurant_id, db: AsyncSession) -> float | None:
    result = await db.execute(
        select(func.avg(Order.total_amount)).where(
            Order.restaurant_id == restaurant_id,
            Order.status.in_([OrderStatus.paid, OrderStatus.completed]),
        )
    )
    avg = result.scalar_one_or_none()
    return float(avg) if avg is not None else None


@router.get("/settings/gift", response_model=SignupGiftOut)
async def get_signup_gift(
    slug: str,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> SignupGiftOut:
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_settings")

    avg_order_value = await _average_order_value(restaurant.id, db)
    return SignupGiftOut(
        gift_type=restaurant.signup_gift_type,
        menu_item_id=restaurant.signup_gift_item_id,
        discount_percent=restaurant.signup_gift_discount_percent,
        average_order_value=avg_order_value,
        discount_suggested=avg_order_value is not None and avg_order_value < DISCOUNT_SUGGESTED_THRESHOLD,
    )


@router.put("/settings/gift", response_model=SignupGiftOut)
async def update_signup_gift(
    slug: str,
    payload: SignupGiftUpdate,
    db: AsyncSession = Depends(get_db),
    staff: User = Depends(get_current_staff),
) -> SignupGiftOut:
    """What's offered to a customer for signing up instead of staying anonymous.

    Redemption/verification lives in the diner app (not built yet) — this just lets the
    restaurant choose either a free menu item, or a % discount on the customer's next order.
    """
    restaurant = await get_restaurant_or_404(slug, db)
    ensure_staff_belongs(restaurant, staff)
    require_capability(restaurant, staff, "manage_settings")

    if payload.gift_type not in ("item", "discount"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "gift_type must be 'item' or 'discount'")

    if payload.gift_type == "item":
        # menu_item_id may be None here — that clears the gift (no item picked yet / turned off).
        if payload.menu_item_id is not None:
            owned_result = await db.execute(
                select(MenuItem)
                .join(MenuSection, MenuItem.section_id == MenuSection.id)
                .where(MenuItem.id == payload.menu_item_id, MenuSection.restaurant_id == restaurant.id)
            )
            if owned_result.scalar_one_or_none() is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found for this restaurant")
        restaurant.signup_gift_type = "item"
        restaurant.signup_gift_item_id = payload.menu_item_id
        restaurant.signup_gift_discount_percent = None
    else:
        if payload.discount_percent is None or not (0 < payload.discount_percent <= 100):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "discount_percent must be between 0 and 100 for gift_type 'discount'"
            )
        restaurant.signup_gift_type = "discount"
        restaurant.signup_gift_discount_percent = payload.discount_percent
        restaurant.signup_gift_item_id = None

    await db.commit()
    await db.refresh(restaurant)

    avg_order_value = await _average_order_value(restaurant.id, db)
    return SignupGiftOut(
        gift_type=restaurant.signup_gift_type,
        menu_item_id=restaurant.signup_gift_item_id,
        discount_percent=restaurant.signup_gift_discount_percent,
        average_order_value=avg_order_value,
        discount_suggested=avg_order_value is not None and avg_order_value < DISCOUNT_SUGGESTED_THRESHOLD,
    )
