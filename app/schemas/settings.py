import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class RolePermissionsOut(BaseModel):
    permissions: dict[str, list[str]]
    capabilities: list[str]
    roles: list[str]


class RolePermissionsUpdate(BaseModel):
    permissions: dict[str, list[str]]


PIN_PATTERN = r"^\d{4}$"


class StaffCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: UserRole
    name: str | None = None
    pin: str | None = Field(default=None, pattern=PIN_PATTERN)


class StaffUpdate(BaseModel):
    role: UserRole
    # Omit entirely to leave the PIN unchanged (checked via model_fields_set, not this default —
    # see update_staff), null to clear it, or a new 4-digit PIN to set/replace it.
    pin: str | None = Field(default=None, pattern=PIN_PATTERN)


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    name: str | None
    role: UserRole
    has_pin: bool = False


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


# Only EN/DE supported for now — Sahar's call 2026-09-18, same scope as the diner app's
# LanguageContext. FR/IT come later alongside real auto-translation.
SUPPORTED_LANGUAGES = ("en", "de")


class LanguageSettingsUpdate(BaseModel):
    languages: list[str]
    default_language: str


class LanguageSettingsOut(BaseModel):
    languages: list[str]
    default_language: str
    supported_languages: list[str] = list(SUPPORTED_LANGUAGES)
