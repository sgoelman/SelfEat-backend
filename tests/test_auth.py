from app.core.security import hash_password
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
