async def test_create_and_list_floors(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    resp = await client.post(f"/restaurants/{slug}/floors", json={"name": "Main Floor"}, headers=headers)
    assert resp.status_code == 201

    list_resp = await client.get(f"/restaurants/{slug}/floors")
    assert list_resp.status_code == 200
    assert [f["name"] for f in list_resp.json()] == ["Main Floor"]


async def test_create_floor_duplicate_name_rejected(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    await client.post(f"/restaurants/{slug}/floors", json={"name": "Patio"}, headers=headers)
    resp = await client.post(f"/restaurants/{slug}/floors", json={"name": "Patio"}, headers=headers)
    assert resp.status_code == 409


async def test_update_floor(client, restaurant):
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]
    create_resp = await client.post(f"/restaurants/{slug}/floors", json={"name": "Patio"}, headers=headers)
    floor_id = create_resp.json()["id"]

    update_resp = await client.patch(f"/restaurants/{slug}/floors/{floor_id}", json={"sort_order": 2}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["sort_order"] == 2
    assert update_resp.json()["name"] == "Patio"


async def test_delete_floor_unassigns_its_tables(client, restaurant):
    """Deleting a floor must not delete or orphan the tables on it — they fall back to floor_id=None."""
    slug = restaurant["slug"]
    headers = restaurant["owner_headers"]

    floor_resp = await client.post(f"/restaurants/{slug}/floors", json={"name": "Patio"}, headers=headers)
    floor_id = floor_resp.json()["id"]

    table_resp = await client.post(
        f"/restaurants/{slug}/tables", json={"number": 1, "floor_id": floor_id}, headers=headers
    )
    table_id = table_resp.json()["id"]
    assert table_resp.json()["floor_id"] == floor_id

    delete_resp = await client.delete(f"/restaurants/{slug}/floors/{floor_id}", headers=headers)
    assert delete_resp.status_code == 204

    tables_resp = await client.get(f"/restaurants/{slug}/tables")
    assert tables_resp.status_code == 200
    remaining = tables_resp.json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == table_id
    assert remaining[0]["floor_id"] is None


async def test_delete_floor_not_found(client, restaurant):
    import uuid

    resp = await client.delete(f"/restaurants/{restaurant['slug']}/floors/{uuid.uuid4()}", headers=restaurant["owner_headers"])
    assert resp.status_code == 404
