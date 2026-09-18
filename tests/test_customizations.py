async def _seed_item_with_modifiers(client, slug, headers):
    """A burger with a required size choice and an optional "remove" group — mirrors the
    ingredient-removal pattern from the "no pickles" request this feature was built for."""
    section_resp = await client.post(f"/restaurants/{slug}/sections", json={"name": {"en": "Mains"}}, headers=headers)
    item_resp = await client.post(
        f"/restaurants/{slug}/items",
        json={
            "section_id": section_resp.json()["id"],
            "name": {"en": "Burger"},
            "price": 12.0,
            "customizations": [
                {
                    "id": "size",
                    "name": {"en": "Size"},
                    "selection_type": "single_required",
                    "options": [
                        {"id": "regular", "label": {"en": "Regular"}, "price_delta": 0},
                        {"id": "large", "label": {"en": "Large"}, "price_delta": 2.5},
                    ],
                },
                {
                    "id": "remove",
                    "name": {"en": "Remove"},
                    "selection_type": "multi",
                    "min_select": 0,
                    "max_select": 3,
                    "options": [
                        {"id": "pickles", "label": {"en": "Pickles"}, "price_delta": 0},
                        {"id": "onions", "label": {"en": "Onions"}, "price_delta": 0},
                        {"id": "cheese", "label": {"en": "Cheese"}, "price_delta": 0},
                    ],
                },
            ],
        },
        headers=headers,
    )
    assert item_resp.status_code == 201, item_resp.text
    return item_resp.json()


async def test_menu_item_customizations_round_trip(client, restaurant):
    item = await _seed_item_with_modifiers(client, restaurant["slug"], restaurant["owner_headers"])
    assert item["customizations"][0]["id"] == "size"
    assert item["customizations"][0]["selection_type"] == "single_required"
    assert item["customizations"][1]["options"][0]["id"] == "pickles"


async def test_menu_item_rejects_single_type_group_with_max_select_above_one(client, restaurant):
    section_resp = await client.post(
        f"/restaurants/{restaurant['slug']}/sections", json={"name": {"en": "Mains"}}, headers=restaurant["owner_headers"]
    )
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/items",
        json={
            "section_id": section_resp.json()["id"],
            "name": {"en": "Bad item"},
            "price": 5,
            "customizations": [
                {
                    "id": "size",
                    "name": {"en": "Size"},
                    "selection_type": "single_optional",
                    "max_select": 2,
                    "options": [{"id": "a", "label": {"en": "A"}}],
                }
            ],
        },
        headers=restaurant["owner_headers"],
    )
    assert resp.status_code == 422


async def test_order_resolves_valid_selection_and_applies_price_delta(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [
                        {"group_id": "size", "option_ids": ["large"]},
                        {"group_id": "remove", "option_ids": ["pickles", "onions"]},
                    ],
                    "note": "extra napkins please",
                }
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    order_item = resp.json()["items"][0]
    assert order_item["unit_price"] == 12.0 + 2.5  # large surcharge applied
    assert order_item["note"] == "extra napkins please"

    selections = {(s["group_id"], s["option_id"]) for s in order_item["customizations"]}
    assert selections == {("size", "large"), ("remove", "pickles"), ("remove", "onions")}
    # Denormalized — the kitchen ticket can render this directly with no second lookup.
    size_selection = next(s for s in order_item["customizations"] if s["group_id"] == "size")
    assert size_selection["label"] == {"en": "Large"}
    assert size_selection["group_name"] == {"en": "Size"}
    assert size_selection["price_delta"] == 2.5


async def test_order_rejects_missing_required_group(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={"items": [{"menu_item_id": item["id"], "quantity": 1, "customizations": []}]},
    )
    assert resp.status_code == 400


async def test_order_rejects_too_many_selections_for_single_required_group(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [{"group_id": "size", "option_ids": ["regular", "large"]}],
                }
            ]
        },
    )
    assert resp.status_code == 400


async def test_order_rejects_selection_over_group_max(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [
                        {"group_id": "size", "option_ids": ["regular"]},
                        {"group_id": "remove", "option_ids": ["pickles", "onions", "cheese", "cheese"]},
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 400


async def test_order_rejects_unknown_group(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [
                        {"group_id": "size", "option_ids": ["regular"]},
                        {"group_id": "sauce", "option_ids": ["ketchup"]},
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 400


async def test_order_rejects_unknown_option_in_known_group(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)

    resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [{"group_id": "size", "option_ids": ["extra-large"]}],
                }
            ]
        },
    )
    assert resp.status_code == 400


async def test_order_with_item_that_has_no_modifier_groups_needs_no_selection(client, restaurant):
    section_resp = await client.post(
        f"/restaurants/{restaurant['slug']}/sections", json={"name": {"en": "Drinks"}}, headers=restaurant["owner_headers"]
    )
    item_resp = await client.post(
        f"/restaurants/{restaurant['slug']}/items",
        json={"section_id": section_resp.json()["id"], "name": {"en": "Cola"}, "price": 3},
        headers=restaurant["owner_headers"],
    )
    resp = await client.post(
        f"/restaurants/{restaurant['slug']}/orders",
        json={"items": [{"menu_item_id": item_resp.json()["id"], "quantity": 1}]},
    )
    assert resp.status_code == 201
    assert resp.json()["items"][0]["customizations"] == []


async def test_kitchen_queue_surfaces_customizations_and_note(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)
    await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [
                        {"group_id": "size", "option_ids": ["regular"]},
                        {"group_id": "remove", "option_ids": ["pickles"]},
                    ],
                    "note": "no pickles please",
                }
            ]
        },
    )

    resp = await client.get(f"/restaurants/{slug}/kitchen/main", headers=headers)
    assert resp.status_code == 200
    queue_item = resp.json()[0]
    assert queue_item["note"] == "no pickles please"
    assert any(s["option_id"] == "pickles" for s in queue_item["customizations"])


async def test_waiter_display_surfaces_customizations_and_note(client, restaurant):
    slug, headers = restaurant["slug"], restaurant["owner_headers"]
    item = await _seed_item_with_modifiers(client, slug, headers)
    order_resp = await client.post(
        f"/restaurants/{slug}/orders",
        json={
            "items": [
                {
                    "menu_item_id": item["id"],
                    "quantity": 1,
                    "customizations": [{"group_id": "size", "option_ids": ["regular"]}],
                    "note": "birthday candle on top",
                }
            ]
        },
    )
    item_id = order_resp.json()["items"][0]["id"]
    await client.post(f"/order-items/{item_id}/claim", json={"staff_name": "Chef"}, headers=headers)
    await client.post(f"/order-items/{item_id}/ready", headers=headers)

    resp = await client.get(f"/restaurants/{slug}/waiter/display", headers=headers)
    assert resp.status_code == 200
    ready_item = resp.json()["destinations"][0]["items"][0]
    assert ready_item["note"] == "birthday candle on top"
    assert ready_item["customizations"][0]["option_id"] == "regular"
