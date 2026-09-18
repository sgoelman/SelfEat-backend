import uuid

from app.models.order import Order, OrderStatus
from tests.conftest import create_staff_member


async def test_get_role_permissions_defaults(client, restaurant):
    resp = await client.get(f"/restaurants/{restaurant['slug']}/settings/roles", headers=restaurant["owner_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert "manage_menu" in body["permissions"]["owner"]
    assert "waiter" in body["permissions"]
    assert "manage_orders" in body["permissions"]["waiter"]


async def test_update_role_permissions_cannot_strip_owner_capabilities(client, restaurant):
    """Owner must always keep every capability, even if the payload tries to remove some —
    otherwise an owner could accidentally lock themselves out of their own restaurant."""
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    resp = await client.put(
        f"/restaurants/{slug}/settings/roles",
        json={"permissions": {"owner": ["manage_menu"], "waiter": ["manage_orders"]}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["permissions"]["owner"]) == set(body["capabilities"])
    assert body["permissions"]["waiter"] == ["manage_orders"]


async def test_update_role_permissions_drops_unknown_capabilities(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    resp = await client.put(
        f"/restaurants/{slug}/settings/roles",
        json={"permissions": {"waiter": ["manage_orders", "not_a_real_capability"]}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["permissions"]["waiter"] == ["manage_orders"]


async def test_settings_requires_manage_settings_capability(client, restaurant):
    waiter = await create_staff_member(
        client, restaurant["slug"], restaurant["owner_headers"], email="waiter@test.selfeat", password="waiterpass123", role="waiter"
    )
    resp = await client.get(f"/restaurants/{restaurant['slug']}/settings/roles", headers=waiter["headers"])
    assert resp.status_code == 403


async def test_create_and_list_staff(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    create_resp = await client.post(
        f"/restaurants/{slug}/staff",
        json={"email": "chef@test.selfeat", "password": "chefpass123", "role": "chef", "name": "Chef Lee"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["role"] == "chef"

    list_resp = await client.get(f"/restaurants/{slug}/staff", headers=headers)
    assert list_resp.status_code == 200
    emails = {u["email"] for u in list_resp.json()}
    assert {"owner@test.selfeat", "chef@test.selfeat"} == emails


async def test_create_staff_rejects_short_password(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    resp = await client.post(
        f"/restaurants/{slug}/staff",
        json={"email": "shortpass@test.selfeat", "password": "abc123", "role": "waiter", "name": "Short Pass"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_manager_cannot_create_owner_via_staff_endpoint(client, restaurant):
    """A manager has manage_staff by default — without this check they could grant
    themselves (or an accomplice) full owner access by POSTing role=owner directly,
    bypassing the frontend chip picker that only offers non-owner roles."""
    slug = restaurant["slug"]
    manager = await create_staff_member(
        client, slug, restaurant["owner_headers"], email="manager@test.selfeat", password="managerpass123", role="manager"
    )

    resp = await client.post(
        f"/restaurants/{slug}/staff",
        json={"email": "sneaky-owner@test.selfeat", "password": "sneakypass123", "role": "owner"},
        headers=manager["headers"],
    )
    assert resp.status_code == 400


async def test_update_staff_role(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    waiter = await create_staff_member(
        client, slug, headers, email="promote-me@test.selfeat", password="waiterpass123", role="waiter"
    )

    resp = await client.patch(
        f"/restaurants/{slug}/staff/{waiter['user']['id']}",
        json={"role": "manager"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


async def test_update_staff_role_rejects_owner_target_or_role(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    waiter = await create_staff_member(
        client, slug, headers, email="stay-waiter@test.selfeat", password="waiterpass123", role="waiter"
    )

    # Can't promote a staff member to owner.
    resp = await client.patch(
        f"/restaurants/{slug}/staff/{waiter['user']['id']}",
        json={"role": "owner"},
        headers=headers,
    )
    assert resp.status_code == 400

    # Can't change the owner's own role via this endpoint.
    me_resp = await client.get(f"/restaurants/{slug}/staff", headers=headers)
    owner_id = next(u["id"] for u in me_resp.json() if u["role"] == "owner")
    resp = await client.patch(
        f"/restaurants/{slug}/staff/{owner_id}",
        json={"role": "manager"},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_update_signup_gift(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Cola"}, "price": 4.5},
        headers=headers,
    )
    item_id = item_resp.json()["id"]

    gift_resp = await client.put(f"/restaurants/{slug}/settings/gift", json={"menu_item_id": item_id}, headers=headers)
    assert gift_resp.status_code == 200
    assert gift_resp.json()["menu_item_id"] == item_id

    restaurant_resp = await client.get(f"/restaurants/{slug}")
    assert restaurant_resp.json()["signup_gift_item_id"] == item_id

    clear_resp = await client.put(f"/restaurants/{slug}/settings/gift", json={"menu_item_id": None}, headers=headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json()["menu_item_id"] is None


async def test_update_signup_gift_rejects_item_from_another_restaurant(client, restaurant):
    other_resp = await client.post(
        "/restaurants",
        json={"slug": "other-resto", "name": "Other", "owner_email": "other@x.com", "owner_password": "pass12345"},
    )
    assert other_resp.status_code == 201
    other_login = await client.post("/auth/login", json={"email": "other@x.com", "password": "pass12345"})
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    section_resp = await client.post("/restaurants/other-resto/sections", json={"name": {"en": "Drinks"}}, headers=other_headers)
    item_resp = await client.post(
        "/restaurants/other-resto/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Cola"}, "price": 4.5},
        headers=other_headers,
    )
    other_item_id = item_resp.json()["id"]

    resp = await client.put(
        f"/restaurants/{restaurant['slug']}/settings/gift",
        json={"menu_item_id": other_item_id},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 404


async def test_update_signup_gift_discount_type(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    resp = await client.put(
        f"/restaurants/{slug}/settings/gift",
        json={"gift_type": "discount", "discount_percent": 15},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gift_type"] == "discount"
    assert body["discount_percent"] == 15
    assert body["menu_item_id"] is None


async def test_update_signup_gift_switching_to_discount_clears_the_item(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Drinks"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Cola"}, "price": 4.5},
        headers=headers,
    )
    await client.put(
        f"/restaurants/{slug}/settings/gift",
        json={"gift_type": "item", "menu_item_id": item_resp.json()["id"]},
        headers=headers,
    )

    resp = await client.put(
        f"/restaurants/{slug}/settings/gift",
        json={"gift_type": "discount", "discount_percent": 10},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["menu_item_id"] is None
    assert resp.json()["discount_percent"] == 10


async def test_update_signup_gift_rejects_invalid_gift_type(client, restaurant):
    resp = await client.put(
        f"/restaurants/{restaurant['slug']}/settings/gift",
        json={"gift_type": "bogus"},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 422


async def test_update_signup_gift_discount_rejects_missing_or_out_of_range_percent(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    missing = await client.put(f"/restaurants/{slug}/settings/gift", json={"gift_type": "discount"}, headers=headers)
    assert missing.status_code == 422

    zero = await client.put(
        f"/restaurants/{slug}/settings/gift", json={"gift_type": "discount", "discount_percent": 0}, headers=headers
    )
    assert zero.status_code == 422

    too_high = await client.put(
        f"/restaurants/{slug}/settings/gift", json={"gift_type": "discount", "discount_percent": 101}, headers=headers
    )
    assert too_high.status_code == 422

    # 100 is the inclusive upper bound — must be accepted.
    upper_bound = await client.put(
        f"/restaurants/{slug}/settings/gift", json={"gift_type": "discount", "discount_percent": 100}, headers=headers
    )
    assert upper_bound.status_code == 200


async def test_get_signup_gift_with_no_orders_has_no_average(client, restaurant):
    resp = await client.get(f"/restaurants/{restaurant['slug']}/settings/gift", headers=restaurant["owner_headers"])
    assert resp.status_code == 200
    assert resp.json()["average_order_value"] is None
    assert resp.json()["discount_suggested"] is False


async def test_get_signup_gift_computes_average_and_suggests_discount_below_threshold(client, db_session, restaurant):
    """average_order_value only counts paid/completed orders, and discount_suggested flips on once
    that average drops under the $15 guidance threshold (DISCOUNT_SUGGESTED_THRESHOLD in settings.py)."""
    restaurant_id = uuid.UUID(restaurant["restaurant"]["id"])
    db_session.add_all(
        [
            Order(restaurant_id=restaurant_id, status=OrderStatus.paid, total_amount=10.0),
            Order(restaurant_id=restaurant_id, status=OrderStatus.completed, total_amount=12.0),
            Order(restaurant_id=restaurant_id, status=OrderStatus.open, total_amount=1000.0),  # excluded: not paid/completed
        ]
    )
    await db_session.commit()

    resp = await client.get(f"/restaurants/{restaurant['slug']}/settings/gift", headers=restaurant["owner_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["average_order_value"] == 11.0
    assert body["discount_suggested"] is True


async def test_get_signup_gift_does_not_suggest_discount_above_threshold(client, db_session, restaurant):
    restaurant_id = uuid.UUID(restaurant["restaurant"]["id"])
    db_session.add(Order(restaurant_id=restaurant_id, status=OrderStatus.paid, total_amount=40.0))
    await db_session.commit()

    resp = await client.get(f"/restaurants/{restaurant['slug']}/settings/gift", headers=restaurant["owner_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["average_order_value"] == 40.0
    assert body["discount_suggested"] is False


async def test_get_language_settings_defaults(client, restaurant):
    resp = await client.get(f"/restaurants/{restaurant['slug']}/settings/language", headers=restaurant["owner_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_language"] == "en"
    assert body["supported_languages"] == ["en", "de"]


async def test_update_language_settings(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    resp = await client.put(
        f"/restaurants/{slug}/settings/language",
        json={"languages": ["en", "de"], "default_language": "de"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["languages"] == ["en", "de"]
    assert body["default_language"] == "de"

    # Persisted, not just echoed back.
    follow_up = await client.get(f"/restaurants/{slug}/settings/language", headers=headers)
    assert follow_up.json()["default_language"] == "de"


async def test_update_language_settings_rejects_unsupported_language(client, restaurant):
    resp = await client.put(
        f"/restaurants/{restaurant['slug']}/settings/language",
        json={"languages": ["en", "fr"], "default_language": "en"},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 422


async def test_update_language_settings_rejects_default_not_in_languages(client, restaurant):
    resp = await client.put(
        f"/restaurants/{restaurant['slug']}/settings/language",
        json={"languages": ["en"], "default_language": "de"},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 422


async def test_update_language_settings_rejects_empty_languages(client, restaurant):
    resp = await client.put(
        f"/restaurants/{restaurant['slug']}/settings/language",
        json={"languages": [], "default_language": "en"},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 422


async def test_delete_staff(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    created = await create_staff_member(client, slug, headers, email="gone@test.selfeat", password="deleteme123", role="waiter")

    resp = await client.delete(f"/restaurants/{slug}/staff/{created['user']['id']}", headers=headers)
    assert resp.status_code == 204

    remaining = await client.get(f"/restaurants/{slug}/staff", headers=headers)
    assert created["user"]["id"] not in [s["id"] for s in remaining.json()]


async def test_delete_staff_cannot_remove_owner(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    staff_list = await client.get(f"/restaurants/{slug}/staff", headers=headers)
    owner_id = next(s["id"] for s in staff_list.json() if s["role"] == "owner")

    resp = await client.delete(f"/restaurants/{slug}/staff/{owner_id}", headers=headers)
    assert resp.status_code == 400


async def test_delete_staff_cannot_remove_self(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    manager = await create_staff_member(client, slug, headers, email="manager@test.selfeat", password="managerpass1", role="manager")

    resp = await client.delete(f"/restaurants/{slug}/staff/{manager['user']['id']}", headers=manager["headers"])
    assert resp.status_code == 400


async def test_delete_staff_unknown_id_is_404(client, restaurant):
    resp = await client.delete(
        f"/restaurants/{restaurant['slug']}/staff/{uuid.uuid4()}", headers=restaurant["owner_headers"]
    )
    assert resp.status_code == 404
