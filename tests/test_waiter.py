import uuid

from tests.conftest import create_staff_member


async def _place_and_ready_order(client, slug, headers, queue_type="bar", table_id=None, name="Espresso"):
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": name}, "price": 3.8, "queue_type": queue_type},
        headers=headers,
    )
    item_id = item_resp.json()["id"]

    payload = {"items": [{"menu_item_id": item_id, "quantity": 1}]}
    if table_id is not None:
        payload["table_id"] = table_id
    order = (await client.post(f"/restaurants/{slug}/orders", json=payload)).json()
    order_item_id = order["items"][0]["id"]

    await client.post(f"/order-items/{order_item_id}/claim", json={"staff_name": "Chef"}, headers=headers)
    await client.post(f"/order-items/{order_item_id}/ready", headers=headers)
    return order, order_item_id


async def test_waiter_display_groups_ready_items_by_destination(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    table_resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 12}, headers=headers)
    table_id = table_resp.json()["id"]

    order, _ = await _place_and_ready_order(client, slug, headers, queue_type="bar", table_id=table_id, name="Latte")
    # A second item for the SAME table, different queue (kitchen), must land on the same card.
    _, second_item_id = await _place_and_ready_order(client, slug, headers, queue_type="main", table_id=table_id, name="Burger")

    resp = await client.get(f"/restaurants/{slug}/waiter/display", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["destinations"]) == 1
    destination = body["destinations"][0]
    assert destination["table_number"] == 12
    assert destination["pickup_number"] is None
    assert {i["id"] for i in destination["items"]} == {order["items"][0]["id"], second_item_id}


async def test_waiter_display_separates_different_destinations(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    await _place_and_ready_order(client, slug, headers, queue_type="bar", name="Kiosk Cola")
    table_resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 3}, headers=headers)
    await _place_and_ready_order(client, slug, headers, queue_type="bar", table_id=table_resp.json()["id"], name="Table Cola")

    resp = await client.get(f"/restaurants/{slug}/waiter/display", headers=headers)
    assert len(resp.json()["destinations"]) == 2


async def test_waiter_display_excludes_queued_and_in_progress_items(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Still cooking"}, "price": 5, "queue_type": "main"},
        headers=headers,
    )
    await client.post(f"/restaurants/{slug}/orders", json={"items": [{"menu_item_id": item_resp.json()["id"], "quantity": 1}]})

    resp = await client.get(f"/restaurants/{slug}/waiter/display", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["destinations"] == []
    assert body["still_in_kitchen_count"] == 1


async def test_mark_delivered(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    _, item_id = await _place_and_ready_order(client, slug, headers)

    resp = await client.post(f"/order-items/{item_id}/delivered", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"

    # Delivered items drop off the waiter display, same as ready items drop off the kitchen queue.
    display = await client.get(f"/restaurants/{slug}/waiter/display", headers=headers)
    assert display.json()["destinations"] == []


async def test_mark_delivered_rejects_item_not_yet_ready(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Cola"}, "price": 3, "queue_type": "bar"},
        headers=headers,
    )
    order = (
        await client.post(
            f"/restaurants/{slug}/orders", json={"items": [{"menu_item_id": item_resp.json()["id"], "quantity": 1}]}
        )
    ).json()

    resp = await client.post(f"/order-items/{order['items'][0]['id']}/delivered", headers=headers)
    assert resp.status_code == 400


async def test_mark_delivered_not_found(client, restaurant):
    resp = await client.post(f"/order-items/{uuid.uuid4()}/delivered", headers=restaurant["owner_headers"])
    assert resp.status_code == 404


async def test_waiter_display_requires_deliver_orders_capability(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    await client.put(f"/restaurants/{slug}/settings/roles", json={"permissions": {"waiter": []}}, headers=headers)
    waiter = await create_staff_member(client, slug, headers, email="waiter@test.selfeat", password="waiterpass123", role="waiter")

    resp = await client.get(f"/restaurants/{slug}/waiter/display", headers=waiter["headers"])
    assert resp.status_code == 403
