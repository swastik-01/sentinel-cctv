from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://sentinel:change_me_in_production@localhost:5432/sentinel"
    redis_url: str = "redis://localhost:6379/0"
    bus_channel: str = "sentinel:events"   # a second instance (e.g. bench/core_scale.py) uses its own, so tests never reach the live UI
    health_monitor: bool = True            # camera probing loop; off for instances that must not probe (scale benchmark)

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    # Also allow pages served from these hosts: the control room opened from another machine on the LAN, whose address
    # is known only on site. Empty = only cors_origins.
    cors_origin_regex: str = ""
    # G3 (bench/pipeline_gates.md): mark reads below 0.9 and one-character alerts "check the crop" in alerts, search
    # and the journey view. Adopted 8 Oct 2026 after its gate passed (bench/results/g3_wiring.md); false restores the
    # 26 Sep behaviour. An A/B flips this, never the code.
    confidence_marking: bool = True

    jwt_secret: str = "dev_only_replace_me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120

    admin_username: str = "admin"
    admin_password: str = "admin123"
    ingest_key: str = "dev_ingest_key_replace_me"

    mediamtx_host: str = "localhost"
    mediamtx_rtsp_port: int = 8554
    mediamtx_api_port: int = 9997
    mediamtx_whep_port: int = 8889
    mediamtx_hls_port: int = 8888
    catalogue_url: str = "http://localhost:8010"

    health_interval_s: int = 20
    alert_cooldown_s: int = 120
    fuzzy_max_edits: int = Field(1, ge=0, le=3)  # OCR errors tolerated in a plate match
    ageing_years: int = Field(7, ge=1, le=30)    # gap analysis: a camera this old is due for replacement

    enable_face_recognition: bool = False  # deliberately off; see docs/privacy-dpdp.md

    @property
    def pg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def mediamtx_api(self) -> str:
        return f"http://{self.mediamtx_host}:{self.mediamtx_api_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
