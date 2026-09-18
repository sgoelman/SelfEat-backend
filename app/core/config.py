from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://selfeat:selfeat@localhost:5432/selfeat"
    secret_key: str = "change-me-to-a-random-secret"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:3000"
    algorithm: str = "HS256"

    # Diner SSO (Google + Facebook only for now — Apple deferred, see TASKS.md). Empty by default;
    # /auth/social refuses to verify a token for a provider whose credential isn't configured,
    # rather than silently skipping the audience check.
    google_client_id: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
