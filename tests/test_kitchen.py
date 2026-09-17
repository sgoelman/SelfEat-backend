import uuid

from tests.conftest import create_staff_member


async def _place_order(client, slug, headers, queue_type="bar"):
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Espresso"}, "price": 3.8, "queue_type": queue_type},
        headers=headers,
    )
    item_id = item_resp.json()["id"]

    order_resp = await client.post(
        f"/restaurants/{slug}/orders", json={"items": [{"menu_item_id": item_id, "quantity": 1}]}
    )
    return order_resp.json()["items"][0]


async def test_list_queue_shows_queued_items_of_matching_type(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    order_item = await _place_order(client, slug, headers, queue_type="bar")

    resp = await client.get(f"/restaurants/{slug}/kitchen/bar", headers=headers)
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()] == [order_item["id"]]

    other_queue_resp = await client.get(f"/restaurants/{slug}/kitchen/main", headers=headers)
    assert other_queue_resp.json() == []


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
    order_item = await _place_order(client, slug, headers, queue_type="bar")
    item_id = order_item["id"]

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
    order_item = await _place_order(client, restaurant["slug"], restaurant["owner_headers"], queue_type="bar")

    other_resp = await client.post(
        "/restaurants",
        json={"slug": "other-resto", "name": "Other", "owner_email": "other@x.com", "owner_password": "pass12345"},
    )
    assert other_resp.status_code == 201
    other_login = await client.post("/auth/login", json={"email": "other@x.com", "password": "pass12345"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    resp = await client.post(f"/order-items/{order_item['id']}/claim", json={"staff_name": "Intruder"}, headers=other_headers)
    assert resp.status_code == 403
