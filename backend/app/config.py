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

    # T5 트랙: 범용 문서 자동 작성기 (PRD T5_범용문서자동작성기) ---------------
    # Claude API. 시크릿은 환경 변수에서 주입(commit 절대 금지).
    anthropic_api_key: str | None = None
    # 양식 분석/매핑은 Sonnet, 단일 변수 재생성은 Haiku로 라우팅 (PRD 6.3, FR-09).
    form_filler_sonnet_model: str = "claude-sonnet-4-6-20250929"
    form_filler_haiku_model: str = "claude-haiku-4-5-20251022"
    # 매핑 confidence < 0.5인 변수는 자동 채움 거부 → 누락 보강 큐 (PRD FR-04, NFR-04 #2).
    form_filler_min_confidence: float = 0.5
    # 양식 분석에서 50개 이상 변수 추출 시 사용자 경고 (PRD FR-01 수용 기준).
    form_filler_max_variables: int = 50
    # 사용자 업로드 자료 보존 기간 (FR-03). 30일 후 cron으로 hard delete.
    form_filler_upload_retention_days: int = 30
    # 출력 .docx + 사용자 업로드 자료 저장 루트. NAS_OUTPUTS 권장 (FR-06).
    form_filler_output_root: str = "/mnt/nas/NAS_OUTPUTS/form_filler"
    form_filler_upload_root: str = "/mnt/nas/NAS_OUTPUTS/form_filler/uploads"
    # 단일 양식 업로드 한도 (FR-01).
    form_filler_max_form_mb: int = 50
    # Langfuse (관측성, NFR-07). 없으면 트레이스만 비활성화하고 기능은 동작.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
