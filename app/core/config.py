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

    # Pro-tier AI menu-photo extraction (Gemini 2.5 Flash via Vertex AI, TASKS.md). Empty
    # project id by default — menu_extraction.py refuses to call out rather than silently
    # no-op, same pattern as the SSO credentials above.
    gcp_project_id: str = ""
    vertex_ai_location: str = "us-central1"
    # Hard backstop under the agreed $5/mo budget cap, not just a GCP billing alert (which only
    # notifies, doesn't stop spend). Conservative estimate: Gemini 2.5 Flash multimodal input
    # (~1 menu photo) + JSON output for a full menu is roughly $0.004-0.006/call at current
    # published per-token pricing, so 800 calls/mo lands around $3.50-4.80 — under the cap with
    # margin for larger images/retries. Revisit against real GCP billing data once there's usage.
    menu_extraction_monthly_call_cap: int = 800

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
