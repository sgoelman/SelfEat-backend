import uuid

from tests.conftest import create_staff_member


async def _place_order(client, slug, headers, queue_type="bar", table_id=None, name="Espresso"):
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
    order_resp = await client.post(f"/restaurants/{slug}/orders", json=payload)
    return order_resp.json()


async def test_list_queue_shows_queued_items_of_matching_type(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    order = await _place_order(client, slug, headers, queue_type="bar")
    order_item = order["items"][0]

    resp = await client.get(f"/restaurants/{slug}/kitchen/bar", headers=headers)
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()] == [order_item["id"]]

    other_queue_resp = await client.get(f"/restaurants/{slug}/kitchen/main", headers=headers)
    assert other_queue_resp.json() == []


async def test_list_queue_includes_order_context(client, restaurant):
    """Each queue item now carries order_id/pickup_number/table_number so staff know who it's for."""
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    table_resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 7}, headers=headers)
    table_id = table_resp.json()["id"]

    dine_in_order = await _place_order(client, slug, headers, queue_type="bar", table_id=table_id, name="Latte")
    kiosk_order = await _place_order(client, slug, headers, queue_type="bar", name="Mocha")

    resp = await client.get(f"/restaurants/{slug}/kitchen/bar", headers=headers)
    assert resp.status_code == 200
    by_order_id = {i["order_id"]: i for i in resp.json()}

    dine_in_item = by_order_id[dine_in_order["id"]]
    assert dine_in_item["table_number"] == 7
    assert dine_in_item["pickup_number"] is None

    kiosk_item = by_order_id[kiosk_order["id"]]
    assert kiosk_item["table_number"] is None
    assert kiosk_item["pickup_number"] == kiosk_order["pickup_number"]


async def test_list_queue_is_fifo_by_placement_time(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    first = await _place_order(client, slug, headers, queue_type="bar", name="First")
    second = await _place_order(client, slug, headers, queue_type="bar", name="Second")
    third = await _place_order(client, slug, headers, queue_type="bar", name="Third")

    resp = await client.get(f"/restaurants/{slug}/kitchen/bar", headers=headers)
    assert resp.status_code == 200
    order_ids_in_queue = [i["order_id"] for i in resp.json()]
    assert order_ids_in_queue == [first["id"], second["id"], third["id"]]


async def test_list_queue_requires_view_kitchen_queue_capability(client, restaurant):
    # Every default role has view_kitchen_queue except "customer" (not a staff role) — there's no
    # staff role in DEFAULT_ROLE_PERMISSIONS without it, so exercise the capability check by
    # explicitly stripping it via the roles endpoint instead.
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    await client.put(
        f"/restaurants/{slug}/settings/roles", json={"permissions": {"waiter": []}}, headers=headers
    )
    waiter = await create_staff_member(
        client, slug, headers, email="waiter@test.selfeat", password="waiterpass123", role="waiter"
    )

    resp = await client.get(f"/restaurants/{slug}/kitchen/bar", headers=waiter["headers"])
    assert resp.status_code == 403


async def test_claim_and_mark_ready_flow(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    order = await _place_order(client, slug, headers, queue_type="bar")
    item_id = order["items"][0]["id"]

    claim_resp = await client.post(f"/order-items/{item_id}/claim", json={"staff_name": "Alex"}, headers=headers)
    assert claim_resp.status_code == 200
    assert claim_resp.json()["status"] == "in_progress"
    assert claim_resp.json()["assigned_staff_name"] == "Alex"

    ready_resp = await client.post(f"/order-items/{item_id}/ready", headers=headers)
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"

    # A claimed-and-ready item drops out of the active queue listing.
    queue_resp = await client.get(f"/restaurants/{slug}/kitchen/bar", headers=headers)
    assert queue_resp.json() == []


async def test_claim_item_not_found(client, restaurant):
    resp = await client.post(
        f"/order-items/{uuid.uuid4()}/claim", json={"staff_name": "Alex"}, headers=restaurant["owner_headers"]
    )
    assert resp.status_code == 404


async def test_claim_item_rejects_staff_from_another_restaurant(client, restaurant):
    order = await _place_order(client, restaurant["slug"], restaurant["owner_headers"], queue_type="bar")
    order_item = order["items"][0]

    other_resp = await client.post(
        "/restaurants",
        json={"slug": "other-resto", "name": "Other", "owner_email": "other@x.com", "owner_password": "pass12345"},
    )
    assert other_resp.status_code == 201
    other_login = await client.post("/auth/login", json={"email": "other@x.com", "password": "pass12345"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = await client.post(f"/order-items/{order_item['id']}/claim", json={"staff_name": "Intruder"}, headers=other_headers)
    assert resp.status_code == 403


async def _place_order_with_items(client, slug, headers, count, push_token=None, fulfillment_mode=None):
    """Like _place_order but supports multiple items + push_token/fulfillment_mode, for the push
    notification tests below — kept separate rather than extending _place_order so the many
    existing callers of that helper aren't affected."""
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Mains"}}, headers=headers)
    items = []
    for i in range(count):
        item_resp = await client.post(
            f"/restaurants/{slug}/items",
            json={"section_id": section_resp.json()["id"], "name": {"en": f"Dish {i}"}, "price": 9.0, "queue_type": "main"},
            headers=headers,
        )
        items.append(item_resp.json()["id"])

    payload: dict = {"items": [{"menu_item_id": item_id, "quantity": 1} for item_id in items]}
    if push_token is not None:
        payload["push_token"] = push_token
    if fulfillment_mode is not None:
        payload["fulfillment_mode"] = fulfillment_mode
    order_resp = await client.post(f"/restaurants/{slug}/orders", json=payload)
    return order_resp.json()


async def test_mark_ready_pushes_immediately_for_when_ready_order(client, restaurant, monkeypatch):
    calls = []

    async def fake_send_push(token, title, body, data=None):
        calls.append((token, title, body, data))

    monkeypatch.setattr("app.api.routes.kitchen.send_push", fake_send_push)

    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    order = await _place_order_with_items(client, slug, headers, count=1, push_token="ExponentPushToken[fake]")
    item_id = order["items"][0]["id"]

    resp = await client.post(f"/order-items/{item_id}/ready", headers=headers)
    assert resp.status_code == 200

    assert len(calls) == 1
    token, title, body, data = calls[0]
    assert token == "ExponentPushToken[fake]"
    assert "ready" in title.lower()
    assert data["order_id"] == order["id"]


async def test_mark_ready_skips_push_when_no_token(client, restaurant, monkeypatch):
    calls = []
    monkeypatch.setattr("app.api.routes.kitchen.send_push", lambda *a, **k: calls.append((a, k)))

    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    order = await _place_order_with_items(client, slug, headers, count=1)
    item_id = order["items"][0]["id"]

    resp = await client.post(f"/order-items/{item_id}/ready", headers=headers)
    assert resp.status_code == 200
    assert calls == []


async def test_mark_ready_waits_for_all_items_when_all_together(client, restaurant, monkeypatch):
    calls = []

    async def fake_send_push(token, title, body, data=None):
        calls.append((token, title, body, data))

    monkeypatch.setattr("app.api.routes.kitchen.send_push", fake_send_push)

    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    order = await _place_order_with_items(
        client, slug, headers, count=2, push_token="ExponentPushToken[fake]", fulfillment_mode="all_together"
    )
    first_id, second_id = order["items"][0]["id"], order["items"][1]["id"]

    first_resp = await client.post(f"/order-items/{first_id}/ready", headers=headers)
    assert first_resp.status_code == 200
    assert calls == []  # one item still not ready — no push yet

    second_resp = await client.post(f"/order-items/{second_id}/ready", headers=headers)
    assert second_resp.status_code == 200
    assert len(calls) == 1  # now that both are ready, exactly one push fires
