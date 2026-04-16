"""애플리케이션 설정. 환경변수에서 로드.

Design Ref: §10.3 Environment Variables
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정. 앱 시작 시 1회 로드."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -------- 공통 --------
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # -------- Database --------
    database_url: str = Field(..., description="async driver: postgresql+asyncpg://...")
    database_url_sync: str = Field(..., description="sync driver (Alembic용): postgresql+psycopg://...")

    # -------- Redis --------
    redis_url: str = "redis://redis:6379/0"

    # -------- JWT (Sprint 1 auth scope) --------
    jwt_secret_key: str = Field(..., min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 14

    # -------- Claude API (Sprint 2 chat scope) --------
    anthropic_api_key: str = ""

    # -------- CORS --------
    allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """쉼표 구분 문자열을 리스트로 변환."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """싱글턴 설정 객체. FastAPI Depends로 주입."""
    return Settings()  # type: ignore[call-arg]
