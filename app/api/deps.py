import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.restaurant import Restaurant
from app.models.user import STAFF_ROLES, User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


async def get_restaurant_or_404(slug: str, db: AsyncSession) -> Restaurant:
    result = await db.execute(select(Restaurant).where(Restaurant.slug == slug))
    restaurant = result.scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Restaurant not found")
    return restaurant


def ensure_staff_belongs(restaurant: Restaurant, staff: User) -> None:
    if staff.restaurant_id != restaurant.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this restaurant")


async def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    return user


async def get_current_customer_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Anonymous ordering must keep working, so unlike get_current_staff this never raises — a
    missing/invalid/expired token, or a token for a non-customer account, just means "no diner
    is logged in for this request," not an error. Only a genuinely valid customer token attaches
    an identity to the order."""
    if credentials is None:
        return None

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        return None

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.role != UserRole.customer:
        return None

    return user


def require_capability(restaurant: Restaurant, staff: User, capability: str) -> None:
    """Raise 403 unless the restaurant's current role_permissions grants this capability to staff.role."""
    allowed = restaurant.role_permissions.get(staff.role.value, [])
    if capability not in allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Role '{staff.role.value}' does not have '{capability}' permission"
        )
