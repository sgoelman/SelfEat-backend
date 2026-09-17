import uuid

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class RolePermissionsOut(BaseModel):
    permissions: dict[str, list[str]]
    capabilities: list[str]
    roles: list[str]


class RolePermissionsUpdate(BaseModel):
    permissions: dict[str, list[str]]


class StaffCreate(BaseModel):
    email: str
    password: str
    role: UserRole
    name: str | None = None


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    name: str | None
    role: UserRole
