import uuid

from tests.conftest import create_staff_member


async def _create_section(client, slug, headers, name="Drinks"):
    resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": name}}, headers=headers)
    assert resp.status_code == 201
    return resp.json()


async def test_create_section_and_item(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    section = await _create_section(client, slug, headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={"section_id": section["id"], "name": {"en": "Cola"}, "price": 4.5},
        headers=headers,
    )
    assert item_resp.status_code == 201
    assert item_resp.json()["price"] == 4.5

    admin_resp = await client.get(f"/restaurants/{slug}/sections", headers=headers)
    assert admin_resp.status_code == 200
    assert admin_resp.json()[0]["items"][0]["name"]["en"] == "Cola"


async def test_create_item_requires_manage_menu_capability(client, restaurant):
    waiter = await create_staff_member(
        client, restaurant["slug"], restaurant["owner_headers"], email="waiter@test.selfeat", password="waiterpass123", role="waiter"
    )
    section = await _create_section(client, restaurant["slug"], restaurant["owner_headers"])

    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/items",
        json={"section_id": section["id"], "name": {"en": "Cola"}, "price": 4.5},
        headers=waiter["headers"],
    )
    assert resp.status_code == 403


async def test_create_item_rejects_section_from_another_restaurant(client, restaurant):
    section = await _create_section(client, restaurant["slug"], restaurant["owner_headers"])

    other_resp = await client.post(
        "/restaurants",
        json={"slug": "other-resto", "name": "Other", "owner_email": "other@x.com", "owner_password": "pass12345"},
    )
    assert other_resp.status_code == 201
    login_resp = await client.post("/auth/login", json={"email": "other@x.com", "password": "pass12345"})
    other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    resp = await client.post(
        "/restaurants/other-resto/items",
        json={"section_id": section["id"], "name": {"en": "Cola"}, "price": 4.5},
        headers=other_headers,
    )
    assert resp.status_code == 404


async def test_update_item(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    section = await _create_section(client, slug, headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items", json={"section_id": section["id"], "name": {"en": "Cola"}, "price": 4.5}, headers=headers
    )
    item_id = item_resp.json()["id"]

    update_resp = await client.patch(f"/restaurants/{slug}/items/{item_id}", json={"price": 5.0}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["price"] == 5.0


async def test_delete_section_cascades_to_its_items(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    section = await _create_section(client, slug, headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items", json={"section_id": section["id"], "name": {"en": "Cola"}, "price": 4.5}, headers=headers
    )
    item_id = item_resp.json()["id"]

    delete_resp = await client.delete(f"/restaurants/{slug}/sections/{section['id']}", headers=headers)
    assert delete_resp.status_code == 204

    # The item must be gone too — otherwise it'd be an orphaned row with a dangling section_id FK.
    update_resp = await client.patch(f"/restaurants/{slug}/items/{item_id}", json={"price": 1.0}, headers=headers)
    assert update_resp.status_code == 404


async def test_delete_item_not_found(client, restaurant):
    resp = await client.delete(f"/restaurants/{restaurant['slug']}/items/{uuid.uuid4()}", headers=restaurant["owner_headers"])
    assert resp.status_code == 404
