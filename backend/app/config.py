from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tk101:password@localhost:5432/tk101"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    google_youtube_api_key: str | None = None
    internal_api_token: str | None = None

    # NAS 자료 검색 (v0.6.0 PoC) -------------------------------------------------
    # 운영 환경에서 NAS 마운트 경로. 컨테이너에서 호스트 NAS를 bind mount.
    nas_mount_path: str = "/mnt/nas"
    # multilingual-e5-large는 한/영/중 동시 지원, 1024-dim. CPU 환경에서도 동작.
    nas_index_text_model: str = "intfloat/multilingual-e5-large"
    nas_index_batch_size: int = 16
    nas_index_max_file_mb: int = 50
    # 청크는 문자 기반 근사. 토큰 환산 시 약 500 token 수준.
    nas_index_chunk_size: int = 500
    nas_index_chunk_overlap: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
