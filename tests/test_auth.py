import uuid

from sqlalchemy import select

import app.api.routes.auth as auth_routes
from app.core.security import hash_password
from app.core.social_auth import SocialProfile
from app.models.user import User, UserRole


async def test_login_success(client, restaurant):
    resp = await client.post("/auth/login", json={"email": "owner@test.selfeat", "password": "ownerpass123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password(client, restaurant):
    resp = await client.post("/auth/login", json={"email": "owner@test.selfeat", "password": "wrong-password"})
    assert resp.status_code == 401


async def test_login_unknown_email(client):
    resp = await client.post("/auth/login", json={"email": "nobody@test.selfeat", "password": "whatever123"})
    assert resp.status_code == 401


async def test_login_rejects_non_staff_role(client, db_session, restaurant):
    """Customer-role accounts (diner app logins) must not be able to authenticate as staff."""
    customer = User(
        restaurant_id=None,
        role=UserRole.customer,
        email="diner@test.selfeat",
        hashed_password=hash_password("dinerpass123"),
    )
    db_session.add(customer)
    await db_session.commit()

    resp = await client.post("/auth/login", json={"email": "diner@test.selfeat", "password": "dinerpass123"})
    assert resp.status_code == 401


async def test_protected_endpoint_requires_token(client, restaurant):
    resp = await client.get(f"/restaurants/{restaurant['slug']}/staff")
    assert resp.status_code == 401


async def test_protected_endpoint_rejects_garbage_token(client, restaurant):
    resp = await client.get(
        f"/restaurants/{restaurant['slug']}/staff",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


async def test_social_login_rejects_unknown_provider(client):
    resp = await client.post("/auth/social", json={"provider": "twitter", "token": "x"})
    assert resp.status_code == 400


async def test_social_login_creates_new_customer(client, db_session, monkeypatch):
    async def fake_verify(token: str) -> SocialProfile:
        return SocialProfile(provider_user_id="google-sub-1", email="diner@example.com", name="Dana Diner")

    monkeypatch.setattr(auth_routes, "verify_google_id_token", fake_verify)
    resp = await client.post("/auth/social", json={"provider": "google", "token": "whatever"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_new_user"] is True
    assert body["email"] == "diner@example.com"
    assert body["name"] == "Dana Diner"
    assert body["access_token"]

    result = await db_session.execute(select(User).where(User.id == uuid.UUID(body["user_id"])))
    user = result.scalar_one()
    assert user.role == UserRole.customer
    assert user.auth_provider == "google"
    assert user.provider_user_id == "google-sub-1"
    assert user.restaurant_id is None


async def test_social_login_repeat_finds_same_user(client, monkeypatch):
    """Same provider identity on a second login must return the existing account, not a duplicate."""

    async def fake_verify(token: str) -> SocialProfile:
        return SocialProfile(provider_user_id="google-sub-2", email="repeat@example.com", name="Rae Peat")

    monkeypatch.setattr(auth_routes, "verify_google_id_token", fake_verify)
    first = await client.post("/auth/social", json={"provider": "google", "token": "t1"})
    second = await client.post("/auth/social", json={"provider": "google", "token": "t2"})

    assert first.json()["is_new_user"] is True
    assert second.json()["is_new_user"] is False
    assert first.json()["user_id"] == second.json()["user_id"]


async def test_social_login_drops_email_on_collision(client, db_session, monkeypatch):
    """email is globally unique across all account types — a new social user whose provider email
    already belongs to someone else must still succeed, just without that email attached."""
    existing = User(role=UserRole.customer, email="taken@example.com", is_anonymous=True)
    db_session.add(existing)
    await db_session.commit()

    async def fake_verify(token: str) -> SocialProfile:
        return SocialProfile(provider_user_id="fb-sub-1", email="taken@example.com", name="Cole Lider")

    monkeypatch.setattr(auth_routes, "verify_facebook_access_token", fake_verify)
    resp = await client.post("/auth/social", json={"provider": "facebook", "token": "whatever"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] is None
    assert resp.json()["is_new_user"] is True
