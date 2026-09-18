import uuid

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SocialLoginRequest(BaseModel):
    provider: str  # "google" | "facebook"
    token: str  # Google: id_token from the client SDK. Facebook: access_token.


class SocialLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    name: str | None
    email: str | None
    is_new_user: bool
