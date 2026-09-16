"""Seed a demo restaurant with a menu, a table, and staff login.

Run with: python -m app.seed
"""

import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.core.security import hash_password
from app.models.base import Base
from app.models.menu import MenuItem, MenuSection, QueueType
from app.models.restaurant import Restaurant
from app.models.table import RestaurantTable
from app.models.user import User, UserRole


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        restaurant = Restaurant(slug="demo-lakeside", name="Demo Lakeside Bar", languages=["en", "de"])
        db.add(restaurant)
        await db.flush()

        owner = User(
            restaurant_id=restaurant.id,
            role=UserRole.owner,
            email="owner@demo.selfeat",
            hashed_password=hash_password("demopass123"),
        )
        db.add(owner)

        table = RestaurantTable(restaurant_id=restaurant.id, number=1, shape="round", pos_x=100, pos_y=100)
        db.add(table)

        drinks = MenuSection(restaurant_id=restaurant.id, name={"en": "Drinks", "de": "Getränke"}, sort_order=0)
        db.add(drinks)
        await db.flush()

        db.add_all(
            [
                MenuItem(
                    section_id=drinks.id,
                    name={"en": "Cola", "de": "Cola"},
                    price=4.5,
                    queue_type=QueueType.pre_ready,
                    is_vegan=True,
                ),
                MenuItem(
                    section_id=drinks.id,
                    name={"en": "Espresso", "de": "Espresso"},
                    price=3.8,
                    queue_type=QueueType.bar,
                    is_vegan=True,
                    supports_delayed_serve=True,
                ),
            ]
        )

        await db.commit()
        print(f"Seeded restaurant '{restaurant.slug}' — owner login: owner@demo.selfeat / demopass123")


if __name__ == "__main__":
    asyncio.run(seed())
