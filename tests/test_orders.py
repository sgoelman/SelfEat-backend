import uuid

import pytest


async def _seed_menu_item(client, slug, headers, price=4.5, name="Cola"):
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": name}, "price": price},
        headers=headers,
    )
    return item_resp.json()


async def test_create_order_computes_total_from_items_and_tip(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    item = await _seed_menu_item(client, slug, headers, price=4.5)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={"tip_amount": 2.0, "items": [{"menu_item_id": item["id"], "quantity": 3}]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total_amount"] == 4.5 * 3 + 2.0
    assert body["items"][0]["unit_price"] == 4.5
    assert body["items"][0]["quantity"] == 3
    assert body["status"] == "open"


async def test_create_order_is_unauthenticated_by_default(client, restaurant):
    """Ordering happens from a customer's phone via QR code — no staff login involved."""
    item = await _seed_menu_item(client, restaurant["slug"], restaurant["owner_headers"])
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/orders",
        json={"items": [{"menu_item_id": item["id"], "quantity": 1}]},
    )
    assert resp.status_code == 201


async def test_create_order_rejects_empty_items(client, restaurant):
    resp = await client.post(f"/restaurants/{restaurant['slug']}/orders", json={"items": []})
    assert resp.status_code == 400


async def test_create_order_rejects_unknown_menu_item(client, restaurant):
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/orders",
        json={"items": [{"menu_item_id": str(uuid.uuid4()), "quantity": 1}]},
    )
    assert resp.status_code == 404


async def test_create_order_rejects_unknown_restaurant(client):
    resp = await client.post(
        "/restaurants/does-not-exist/orders",
        json={"items": [{"menu_item_id": str(uuid.uuid4()), "quantity": 1}]},
    )
    assert resp.status_code == 404


async def test_get_order(client, restaurant):
    item = await _seed_menu_item(client, restaurant["slug"], restaurant["owner_headers"])
    create_resp = await client.post(
        f"/restaurants/{restaurant['slug']}/orders",
        json={"items": [{"menu_item_id": item["id"], "quantity": 1}]},
    )
    order_id = create_resp.json()["id"]

    get_resp = await client.get(f"/orders/{order_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == order_id


async def test_get_order_not_found(client):
    resp = await client.get(f"/orders/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_create_order_rejects_menu_item_from_another_restaurant(client, restaurant):
    other_resp = await client.post(
        "/restaurants",
        json={"slug": "other-resto", "name": "Other", "owner_email": "other@x.com", "owner_password": "pass12345"},
    )
    assert other_resp.status_code == 201
    other_login = await client.post("/auth/login", json={"email": "other@x.com", "password": "pass12345"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    other_item = await _seed_menu_item(client, "other-resto", other_headers, name="Other's Cola")

    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/orders",
        json={"items": [{"menu_item_id": other_item["id"], "quantity": 1}]},
    )
    assert resp.status_code == 404
