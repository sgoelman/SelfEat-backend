from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models.base import Base


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def db_engine():
    # A single shared in-memory connection (StaticPool) so every session in a test — the
    # fixtures below and the app's request-scoped sessions — sees the same data.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def restaurant(client: AsyncClient) -> dict:
    """A fresh restaurant with an owner account, plus the owner's bearer token."""
    resp = await client.post(
        "/restaurants",
        json={
            "slug": "test-resto",
            "name": "Test Resto",
            "owner_email": "owner@test.selfeat",
            "owner_password": "ownerpass123",
        },
    )
    assert resp.status_code == 201, resp.text
    restaurant_data = resp.json()

    login_resp = await client.post("/auth/login", json={"email": "owner@test.selfeat", "password": "ownerpass123"})
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    return {
        "restaurant": restaurant_data,
        "slug": restaurant_data["slug"],
        "owner_token": token,
        "owner_headers": auth_headers(token),
    }


async def create_staff_member(client: AsyncClient, slug: str, owner_headers: dict, *, email: str, password: str, role: str) -> dict:
    """Create a staff member of a given role via the API and log them in. Returns token + headers."""
    resp = await client.post(
        f"/restaurants/{slug}/staff",
        json={"email": email, "password": password, "role": role},
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text

    login_resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    return {"user": resp.json(), "token": token, "headers": auth_headers(token)}
