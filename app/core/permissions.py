from app.models.user import UserRole

# Every capability a staff action in the app can require. Kept flat and small
# on purpose — this is the set restaurant owners configure per role in Settings.
CAPABILITIES = [
    "manage_menu",
    "manage_tables",
    "manage_staff",
    "manage_settings",
    "view_kitchen_queue",
    "claim_kitchen_items",
    "manage_orders",
]

# Sensible restaurant-world defaults, applied when a restaurant is created.
# Editable per restaurant afterwards via PUT /restaurants/{slug}/settings/roles.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    UserRole.owner.value: list(CAPABILITIES),
    UserRole.manager.value: [
        "manage_menu",
        "manage_tables",
        "manage_staff",
        "view_kitchen_queue",
        "claim_kitchen_items",
        "manage_orders",
    ],
    UserRole.waiter.value: ["view_kitchen_queue", "manage_orders"],
    UserRole.kitchen.value: ["view_kitchen_queue", "claim_kitchen_items"],
    UserRole.chef.value: ["view_kitchen_queue", "claim_kitchen_items", "manage_menu"],
}


def default_role_permissions() -> dict[str, list[str]]:
    """Fresh copy for use as a SQLAlchemy column default (avoids the mutable-default pitfall)."""
    return {role: list(caps) for role, caps in DEFAULT_ROLE_PERMISSIONS.items()}
