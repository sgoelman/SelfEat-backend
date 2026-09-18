from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
FACEBOOK_DEBUG_TOKEN_URL = "https://graph.facebook.com/debug_token"
FACEBOOK_GRAPH_ME_URL = "https://graph.facebook.com/me"


@dataclass
class SocialProfile:
    provider_user_id: str
    email: str | None
    name: str | None


async def verify_google_id_token(id_token: str) -> SocialProfile:
    """Google's tokeninfo endpoint both verifies the token's signature/expiry and returns its
    claims in one call — no need to fetch/cache Google's public keys ourselves. Checking `aud`
    confirms the token was issued for *our* OAuth client, not some unrelated Google app."""
    if not settings.google_client_id:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Google sign-in isn't configured on this server")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token})

    if resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google sign-in token")

    data = resp.json()
    if data.get("aud") != settings.google_client_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google token was not issued for this app")

    return SocialProfile(provider_user_id=data["sub"], email=data.get("email"), name=data.get("name"))


async def verify_facebook_access_token(access_token: str) -> SocialProfile:
    """Facebook access tokens aren't self-contained JWTs, and calling /me alone would accept a
    valid token from *any* Facebook app, not just ours — debug_token (using our own app
    access token, app_id|app_secret) is what confirms this token was actually issued for our
    Facebook app before we trust it."""
    if not settings.facebook_app_id or not settings.facebook_app_secret:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Facebook sign-in isn't configured on this server")

    app_access_token = f"{settings.facebook_app_id}|{settings.facebook_app_secret}"

    async with httpx.AsyncClient(timeout=10) as client:
        debug_resp = await client.get(
            FACEBOOK_DEBUG_TOKEN_URL, params={"input_token": access_token, "access_token": app_access_token}
        )
        if debug_resp.status_code != 200:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Facebook sign-in token")
        debug_data = debug_resp.json().get("data", {})
        if not debug_data.get("is_valid") or str(debug_data.get("app_id")) != settings.facebook_app_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Facebook token was not issued for this app")

        profile_resp = await client.get(FACEBOOK_GRAPH_ME_URL, params={"fields": "id,name,email", "access_token": access_token})
        if profile_resp.status_code != 200:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not read Facebook profile")
        profile = profile_resp.json()

    return SocialProfile(provider_user_id=profile["id"], email=profile.get("email"), name=profile.get("name"))
