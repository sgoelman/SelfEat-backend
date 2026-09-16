import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.restaurant import Restaurant
from app.models.user import User, UserRole

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
    if user is None or user.role not in (UserRole.owner, UserRole.staff):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    return user
