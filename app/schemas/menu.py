import uuid
from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.menu import QueueType


class ModifierOption(BaseModel):
    id: str
    label: dict[str, str]
    price_delta: float = 0


class ModifierGroup(BaseModel):
    """A restaurant-defined set of choices for a menu item, e.g. "Choice of sauce" or an
    ingredient-removal group like "Remove" for a burger's default toppings. Mirrors the
    Uber Eats/DoorDash "modifier group" pattern (PM/PO competitive benchmark, 2026-09-18) rather
    than a single free-text note, so the kitchen ticket gets an unambiguous, machine-readable
    selection instead of prose staff have to interpret."""

    id: str
    name: dict[str, str]
    selection_type: Literal["single_required", "single_optional", "multi"]
    min_select: int = 0
    max_select: int | None = None
    options: list[ModifierOption]

    @model_validator(mode="after")
    def _check_cardinality(self) -> "ModifierGroup":
        if self.selection_type in ("single_required", "single_optional") and (self.min_select > 1 or (self.max_select is not None and self.max_select > 1)):
            raise ValueError(f"Group '{self.id}': single-selection types can't have min/max above 1")
        if self.max_select is not None and self.max_select < self.min_select:
            raise ValueError(f"Group '{self.id}': max_select can't be less than min_select")
        return self


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
    customizations: list[ModifierGroup] = []
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
    customizations: list[ModifierGroup] | None = None
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
    customizations: list[ModifierGroup]
    supports_delayed_serve: bool
    sort_order: int


class MenuSectionWithItems(MenuSectionOut):
    items: list[MenuItemOut] = []


class ExtractedMenuItemOut(BaseModel):
    """A candidate item pulled from a menu photo (Pro-tier AI extraction) — not yet a real
    MenuItem; the restaurant reviews/edits these client-side before actually creating any."""

    name: dict[str, str]
    description: dict[str, str] = {}
    price: float | None = None


class MenuExtractionResultOut(BaseModel):
    items: list[ExtractedMenuItemOut]
