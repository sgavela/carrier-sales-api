from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Auth
    API_KEY: str = "dev-insecure-key"

    # FMCSA
    FMCSA_WEBKEY: str = ""
    FMCSA_BASE_URL: str = "https://mobile.fmcsa.dot.gov/qc/services/carriers"
    FMCSA_TIMEOUT: float = 5.0
    FMCSA_MOCK: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./data/carrier_sales.db"

    # Server
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # CORS — stored as a comma-separated string, exposed as a list
    CORS_ORIGINS: str = "http://localhost:3000"

    # Negotiation thresholds
    MAX_ROUNDS: int = 3
    MAX_MARGIN_PCT: float = 0.12       # absolute ceiling — broker never pays more than this
    ROUND1_CEILING_PCT: float = 0.12   # max we pay in round 1
    ROUND1_COUNTER_PCT: float = 0.05   # our first counter above loadboard
    ROUND2_CEILING_PCT: float = 0.10   # tighter ceiling in round 2
    ROUND2_BLEND_RATIO: float = 0.75   # how far we move toward carrier in round 2
    ROUND3_ACCEPT_PCT: float = 0.08    # accept anything at or below this in round 3

    @field_validator("LOG_LEVEL")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        return v.upper()

    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
