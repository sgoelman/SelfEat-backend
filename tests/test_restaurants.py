import datetime as datetime_module


async def test_create_restaurant(client):
    resp = await client.post(
        "/restaurants",
        json={"slug": "brand-new", "name": "Brand New", "owner_email": "o@x.com", "owner_password": "pass12345"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "brand-new"
    assert body["languages"] == ["en"]
    assert body["signup_gift_item_id"] is None


async def test_create_restaurant_duplicate_slug_rejected(client, restaurant):
    resp = await client.post(
        "/restaurants",
        json={
            "slug": restaurant["slug"],
            "name": "Dup",
            "owner_email": "dup@x.com",
            "owner_password": "pass12345",
        },
    )
    assert resp.status_code == 409


async def test_get_restaurant_not_found(client):
    resp = await client.get("/restaurants/does-not-exist")
    assert resp.status_code == 404


async def test_get_restaurant(client, restaurant):
    resp = await client.get(f"/restaurants/{restaurant['slug']}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == restaurant["slug"]


async def test_public_menu_filters_items_outside_availability_window(client, restaurant, monkeypatch):
    """The public /menu endpoint must hide items outside their available_from/available_to window,
    while the admin /sections endpoint (tested elsewhere) shows everything regardless of time."""
    from app.api.routes import restaurants as restaurants_route

    fixed_now = datetime_module.datetime(2026, 1, 1, 12, 0, tzinfo=datetime_module.timezone.utc)

    class FixedDatetime(datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(restaurants_route, "datetime", FixedDatetime)

    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Mains"}}, headers=headers)
    assert section_resp.status_code == 201
    section_id = section_resp.json()["id"]

    await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_id, "name": {"en": "Always Available"}, "price": 9.5},
        headers=headers,
    )
    await client.post(
        f"/restaurants/{slug}/items",
        json={
            "section_id": section_id,
            "name": {"en": "Breakfast Only"},
            "price": 5.0,
            "available_from": "06:00:00",
            "available_to": "10:00:00",
        },
        headers=headers,
    )
    await client.post(
        f"/restaurants/{slug}/items",
        json={
            "section_id": section_id,
            "name": {"en": "Lunch Only"},
            "price": 7.0,
            "available_from": "11:00:00",
            "available_to": "14:00:00",
        },
        headers=headers,
    )

    menu_resp = await client.get(f"/restaurants/{slug}/menu")
    assert menu_resp.status_code == 200
    names = {item["name"]["en"] for item in menu_resp.json()[0]["items"]}
    assert names == {"Always Available", "Lunch Only"}
