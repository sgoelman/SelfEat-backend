import uuid
from datetime import time

from pydantic import BaseModel, ConfigDict

from app.models.menu import QueueType


class MenuSectionCreate(BaseModel):
    name: dict[str, str]
    sort_order: int = 0


class MenuSectionUpdate(BaseModel):
    name: dict[str, str] | None = None
    sort_order: int | None = None


class MenuSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: dict[str, str]
    sort_order: int


class MenuItemCreate(BaseModel):
    section_id: uuid.UUID
    name: dict[str, str]
    description: dict[str, str] = {}
    price: float
    picture_url: str | None = None
    is_vegan: bool = False
    diet_tags: list[str] = []
    allergens: list[str] = []
    available_from: time | None = None
    available_to: time | None = None
    queue_type: QueueType = QueueType.main
    customizations: list[dict] = []
    supports_delayed_serve: bool = False
    sort_order: int = 0


class MenuItemUpdate(BaseModel):
    name: dict[str, str] | None = None
    description: dict[str, str] | None = None
    price: float | None = None
    picture_url: str | None = None
    is_vegan: bool | None = None
    diet_tags: list[str] | None = None
    allergens: list[str] | None = None
    available_from: time | None = None
    available_to: time | None = None
    queue_type: QueueType | None = None
    customizations: list[dict] | None = None
    supports_delayed_serve: bool | None = None
    sort_order: int | None = None


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    name: dict[str, str]
    description: dict[str, str]
    price: float
    picture_url: str | None
    is_vegan: bool
    diet_tags: list[str]
    allergens: list[str]
    available_from: time | None
    available_to: time | None
    queue_type: QueueType
    customizations: list[dict]
    supports_delayed_serve: bool
    sort_order: int


class MenuSectionWithItems(MenuSectionOut):
    items: list[MenuItemOut] = []
