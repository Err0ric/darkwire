from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://darkwire:darkwire@localhost:5432/darkwire"
    port: int = 8000
    ingest_interval_minutes: int = 15
    ingest_enabled: bool = True
    enrich_interval_minutes: int = 15
    # Optional. Raises NVD's limit from 5 to 50 requests per 30 s.
    nvd_api_key: str | None = None
    cors_origins: str = "http://localhost:3000,https://darkwire.tech"
    # Vercel production and preview deployments. Matched against the full Origin.
    cors_origin_regex: str | None = r"https://[a-z0-9-]+\.vercel\.app"

    @property
    def async_database_url(self) -> str:
        """Railway hands out postgres:// or postgresql://. asyncpg needs its own scheme."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
