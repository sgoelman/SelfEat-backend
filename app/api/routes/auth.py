from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.core.social_auth import SocialProfile, verify_facebook_access_token, verify_google_id_token
from app.models.user import STAFF_ROLES, User, UserRole
from app.schemas.auth import LoginRequest, SocialLoginRequest, SocialLoginResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    if user.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


async def _find_or_create_social_user(db: AsyncSession, provider: str, profile: SocialProfile) -> tuple[User, bool]:
    existing = await db.execute(
        select(User).where(User.auth_provider == provider, User.provider_user_id == profile.provider_user_id)
    )
    user = existing.scalar_one_or_none()
    if user is not None:
        return user, False

    # `email` is globally unique across every account type (staff included) — if this diner's
    # provider email already belongs to some other row, drop it rather than fail the signup.
    # Rare (a second provider or a staff account happening to share the address), and losing the
    # email on a brand-new anonymous-by-default customer row costs nothing important.
    safe_email = profile.email
    if safe_email is not None:
        taken = await db.execute(select(User).where(User.email == safe_email))
        if taken.scalar_one_or_none() is not None:
            safe_email = None

    user = User(
        role=UserRole.customer,
        restaurant_id=None,
        auth_provider=provider,
        provider_user_id=profile.provider_user_id,
        email=safe_email,
        name=profile.name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True


@router.post("/social", response_model=SocialLoginResponse)
async def social_login(payload: SocialLoginRequest, db: AsyncSession = Depends(get_db)) -> SocialLoginResponse:
    """Optional diner sign-in — anonymous ordering still works without it. Google/Facebook only
    for now; Apple deferred (see TASKS.md) until closer to an actual App Store submission."""
    if payload.provider == "google":
        profile = await verify_google_id_token(payload.token)
    elif payload.provider == "facebook":
        profile = await verify_facebook_access_token(payload.token)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "provider must be 'google' or 'facebook'")

    user, is_new_user = await _find_or_create_social_user(db, payload.provider, profile)

    token = create_access_token(subject=str(user.id))
    return SocialLoginResponse(
        access_token=token,
        user_id=user.id,
        name=user.name,
        email=user.email,
        is_new_user=is_new_user,
    )
