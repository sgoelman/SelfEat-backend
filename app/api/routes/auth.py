from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_restaurant_or_404
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.core.social_auth import SocialProfile, verify_facebook_access_token, verify_google_id_token
from app.models.user import STAFF_ROLES, User, UserRole
from app.schemas.auth import LoginRequest, PinLoginRequest, SocialLoginRequest, SocialLoginResponse, TokenResponse

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


@router.post("/pin-login/{slug}", response_model=TokenResponse)
async def pin_login(slug: str, payload: PinLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Daily floor-staff login (PM/PO's staff-login-UX research, TASKS.md): the device is set up
    for one restaurant once (the slug comes from that device-level setup, not typed per login),
    so a waiter/kitchen/chef just enters their PIN — no email, no restaurant identifier.

    PINs are hashed per-user (see User.pin_hash), so there's no direct lookup — this scans the
    restaurant's staff and bcrypt-checks each one with a PIN set. Fine at normal staff-roster
    sizes; _pin_collides_with_other_staff (routes/settings.py) prevents two staff sharing a PIN,
    which is what would make this scan ambiguous.
    """
    restaurant = await get_restaurant_or_404(slug, db)

    result = await db.execute(select(User).where(User.restaurant_id == restaurant.id, User.pin_hash.is_not(None)))
    candidates = result.scalars().all()

    match = next((u for u in candidates if verify_password(payload.pin, u.pin_hash)), None)
    if match is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect PIN")

    token = create_access_token(subject=str(match.id))
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
