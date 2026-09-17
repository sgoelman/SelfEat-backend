import uuid

from pydantic import BaseModel, ConfigDict


class RestaurantPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    languages: list[str]
    signup_gift_item_id: uuid.UUID | None = None


class RestaurantCreate(BaseModel):
    slug: str
    name: str
    languages: list[str] = ["en"]
    owner_email: str
    owner_password: str
