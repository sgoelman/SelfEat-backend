from tests.conftest import create_staff_member


async def test_create_table(client, restaurant):
    slug = restaurant["slug"]
    resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 1}, headers=restaurant["owner_headers"])
    assert resp.status_code == 201
    body = resp.json()
    assert body["number"] == 1
    assert body["restaurant_id"] == restaurant["restaurant"]["id"]
    assert body["qr_token"]


async def test_create_table_requires_manage_tables_capability(client, restaurant):
    """A waiter has no manage_tables capability by default (see DEFAULT_ROLE_PERMISSIONS)."""
    waiter = await create_staff_member(
        client, restaurant["slug"], restaurant["owner_headers"], email="waiter@test.selfeat", password="waiterpass123", role="waiter"
    )
    resp = await client.post(f"/restaurants/{restaurant['slug']}/tables", json={"number": 1}, headers=waiter["headers"])
    assert resp.status_code == 403


async def test_create_table_duplicate_number_rejected(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    await client.post(f"/restaurants/{slug}/tables", json={"number": 1}, headers=headers)
    resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 1}, headers=headers)
    assert resp.status_code == 409


async def test_create_table_unknown_floor_rejected(client, restaurant):
    import uuid

    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/tables",
        json={"number": 1, "floor_id": str(uuid.uuid4())},
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 404


async def test_update_table(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    create_resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 1, "seats": 2}, headers=headers)
    table_id = create_resp.json()["id"]

    update_resp = await client.patch(f"/restaurants/{slug}/tables/{table_id}", json={"seats": 6}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["seats"] == 6
    assert update_resp.json()["number"] == 1  # untouched fields stay as-is


async def test_update_table_not_found(client, restaurant):
    import uuid

    resp = await client.patch(
        f"/restaurants/{restaurant['slug']}/tables/{uuid.uuid4()}", json={"seats": 6}, headers=restaurant["owner_headers"]
    )
    assert resp.status_code == 404


async def test_delete_table(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    create_resp = await client.post(f"/restaurants/{slug}/tables", json={"number": 1}, headers=headers)
    table_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/restaurants/{slug}/tables/{table_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/restaurants/{slug}/tables")
    assert list_resp.json() == []


async def test_table_from_another_restaurant_is_not_visible(client, restaurant):
    """A staff member cannot update/delete a table belonging to a different restaurant, even
    if they know its id — the query scopes by restaurant_id, so it looks like a 404."""
    slug_a = restaurant["slug"]
    headers_a = restaurant["owner_headers"]
    table_resp = await client.post(f"/restaurants/{slug_a}/tables", json={"number": 1}, headers=headers_a)
    table_id = table_resp.json()["id"]

    other_resp = await client.post(
        "/restaurants",
        json={"slug": "other-resto", "name": "Other", "owner_email": "other@x.com", "owner_password": "pass12345"},
    )
    assert other_resp.status_code == 201
    login_resp = await client.post("/auth/login", json={"email": "other@x.com", "password": "pass12345"})
    other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    resp = await client.patch(
        f"/restaurants/other-resto/tables/{table_id}", json={"seats": 6}, headers=other_headers
    )
    assert resp.status_code == 404
