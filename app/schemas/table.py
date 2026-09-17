import uuid

from pydantic import BaseModel, ConfigDict


class TableCreate(BaseModel):
    number: int
    floor_id: uuid.UUID | None = None
    shape: str = "round"
    material: str = "wood"
    color: str = "#c8a15a"
    seats: int = 2
    pos_x: float = 0
    pos_y: float = 0
    width: float = 80
    height: float = 80


class TableUpdate(BaseModel):
    number: int | None = None
    floor_id: uuid.UUID | None = None
    shape: str | None = None
    material: str | None = None
    color: str | None = None
    seats: int | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    width: float | None = None
    height: float | None = None


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    floor_id: uuid.UUID | None
    number: int
    shape: str
    material: str
    color: str
    seats: int
    pos_x: float
    pos_y: float
    width: float
    height: float
    qr_token: str
