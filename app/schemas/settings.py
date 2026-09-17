import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class RolePermissionsOut(BaseModel):
    permissions: dict[str, list[str]]
    capabilities: list[str]
    roles: list[str]


class RolePermissionsUpdate(BaseModel):
    permissions: dict[str, list[str]]


class StaffCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: UserRole
    name: str | None = None


class StaffUpdate(BaseModel):
    role: UserRole


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    name: str | None
    role: UserRole


class SignupGiftUpdate(BaseModel):
    gift_type: str = "item"  # "item" | "discount"
    menu_item_id: uuid.UUID | None = None  # required when gift_type == "item"
    discount_percent: float | None = None  # required when gift_type == "discount"


class SignupGiftOut(BaseModel):
    gift_type: str
    menu_item_id: uuid.UUID | None
    discount_percent: float | None
    average_order_value: float | None  # None if the restaurant has no orders yet
    discount_suggested: bool  # True when average_order_value is known and under the $15 guidance threshold
