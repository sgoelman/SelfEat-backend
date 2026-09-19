import uuid

from sqlalchemy import select

from app.models.menu_extraction import MenuExtractionUsage
from app.models.restaurant import Restaurant
from app.services.menu_extraction import ExtractedMenuItem
from tests.conftest import create_staff_member


async def _set_plan(db_session, restaurant_id: str, plan: str) -> None:
    result = await db_session.execute(select(Restaurant).where(Restaurant.id == uuid.UUID(restaurant_id)))
    row = result.scalar_one()
    row.plan = plan
    await db_session.commit()


def _fake_image_file(name: str = "menu.jpg", content_type: str = "image/jpeg") -> dict:
    return {"file": (name, b"\xff\xd8\xff fake jpeg bytes", content_type)}


async def test_extract_requires_pro_plan(client, restaurant):
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/menu/extract",
        files=_fake_image_file(),
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 403


async def test_extract_requires_manage_menu_capability(client, restaurant, db_session):
    await _set_plan(db_session, restaurant["restaurant"]["id"], "pro")
    waiter = await create_staff_member(
        client, restaurant["slug"], restaurant["owner_headers"], email="waiter@test.selfeat", password="waiterpass123", role="waiter"
    )
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/menu/extract",
        files=_fake_image_file(),
        headers=waiter["headers"],
    )
    assert resp.status_code == 403


async def test_extract_rejects_non_image_content_type(client, restaurant, db_session):
    await _set_plan(db_session, restaurant["restaurant"]["id"], "pro")
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/menu/extract",
        files={"file": ("menu.txt", b"not an image", "text/plain")},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 400


async def test_extract_success_returns_items_and_tracks_usage(client, restaurant, db_session, monkeypatch):
    await _set_plan(db_session, restaurant["restaurant"]["id"], "pro")

    async def fake_extract(image_bytes: bytes, mime_type: str):
        return [
            ExtractedMenuItem(name={"en": "Cola", "de": "Cola"}, description={"en": "", "de": ""}, price=4.5),
            ExtractedMenuItem(name={"en": "Burger", "de": "Burger"}, description={"en": "Beef", "de": "Rind"}, price=15.0),
        ]

    monkeypatch.setattr("app.api.routes.menu.extract_menu_items_from_image", fake_extract)

    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/menu/extract",
        files=_fake_image_file(),
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["name"] == {"en": "Cola", "de": "Cola"}
    assert items[1]["price"] == 15.0

    usage_result = await db_session.execute(select(MenuExtractionUsage))
    usage_rows = usage_result.scalars().all()
    assert len(usage_rows) == 1
    assert usage_rows[0].call_count == 1


async def test_extract_stops_at_monthly_cap(client, restaurant, db_session, monkeypatch):
    from datetime import datetime, timezone

    from app.core.config import settings as app_settings

    await _set_plan(db_session, restaurant["restaurant"]["id"], "pro")
    monkeypatch.setattr(app_settings, "menu_extraction_monthly_call_cap", 1)

    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    db_session.add(MenuExtractionUsage(year_month=year_month, call_count=1))
    await db_session.commit()

    called = False

    async def fake_extract(image_bytes: bytes, mime_type: str):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("app.api.routes.menu.extract_menu_items_from_image", fake_extract)

    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/menu/extract",
        files=_fake_image_file(),
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 429
    assert called is False


async def test_extract_surfaces_extraction_failure_as_502(client, restaurant, db_session, monkeypatch):
    from app.services.menu_extraction import MenuExtractionError

    await _set_plan(db_session, restaurant["restaurant"]["id"], "pro")

    async def failing_extract(image_bytes: bytes, mime_type: str):
        raise MenuExtractionError("boom")

    monkeypatch.setattr("app.api.routes.menu.extract_menu_items_from_image", failing_extract)

    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/menu/extract",
        files=_fake_image_file(),
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 502
