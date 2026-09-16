import uuid

from pydantic import BaseModel, ConfigDict


class TableCreate(BaseModel):
    number: int
    shape: str = "round"
    color: str = "#c8a15a"
    pos_x: float = 0
    pos_y: float = 0
    width: float = 80
    height: float = 80


class TableUpdate(BaseModel):
    number: int | None = None
    shape: str | None = None
    color: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    width: float | None = None
    height: float | None = None


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    restaurant_id: uuid.UUID
    number: int
    shape: str
    color: str
    pos_x: float
    pos_y: float
    width: float
    height: float
    qr_token: str
