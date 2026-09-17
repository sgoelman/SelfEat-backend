import uuid

from pydantic import BaseModel, ConfigDict


class FloorCreate(BaseModel):
    name: str
    sort_order: int = 0


class FloorUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


class FloorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    sort_order: int
