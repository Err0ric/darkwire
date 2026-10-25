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
    # Optional. Row summaries are generated with Claude only when this is set.
    anthropic_api_key: str | None = None
    # Set by Railway on every deploy. Its presence means production: docs off, proxy headers
    # trusted (app/throttle.py).
    railway_environment_name: str | None = None
    # Optional. Lifts the public limit of 100 rows and allows /feed?all_sources (feed audit).
    audit_token: str | None = None
    # Optional. Server-rendered page requests from the web app carry it and skip the per-IP
    # read bucket. Set the same value as API_SERVER_TOKEN on Vercel.
    ssr_token: str | None = None
    # The live merge rules of 2026-10-25 (WIRE_FIXES.md P1): reading item_cves.subject when
    # merging, "tracked as" subject CVEs, KEV alerts re-homing. LIVE_MERGE_RULES=false turns all
    # three off (read at start: Railway restarts the service when a variable changes). Flags are
    # still written. The one-time re-merge (app/p1_remerge.py) always uses the rules.
    live_merge_rules: bool = True

    @property
    def async_database_url(self) -> str:
        """Railway hands out postgres:// or postgresql://. asyncpg needs its own scheme."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix):]
        return url

    @property
    def on_railway(self) -> bool:
        return bool(self.railway_environment_name)


@lru_cache
def get_settings() -> Settings:
    return Settings()
