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
    form_filler_sonnet_model: str = "claude-sonnet-4-6"
    form_filler_haiku_model: str = "claude-haiku-4-5-20251001"
    # 매핑 confidence < 0.5인 변수는 자동 채움 거부 → 누락 보강 큐 (PRD FR-04, NFR-04 #2).
    form_filler_min_confidence: float = 0.5
    # 양식 분석에서 50개 이상 변수 추출 시 사용자 경고 (PRD FR-01 수용 기준).
    form_filler_max_variables: int = 50
    # 사용자 업로드 자료 보존 기간 (FR-03). 30일 후 cron으로 hard delete.
    form_filler_upload_retention_days: int = 30
    # 출력 .docx + 사용자 업로드 자료 저장 루트.
    # NAS는 T2 정책상 read-only 마운트라 별도 docker volume 사용 (form_filler_data).
    form_filler_output_root: str = "/var/lib/form_filler/outputs"
    form_filler_upload_root: str = "/var/lib/form_filler/uploads"
    # 단일 양식 업로드 한도 (FR-01).
    form_filler_max_form_mb: int = 50
    # Langfuse (관측성, NFR-07). 없으면 트레이스만 비활성화하고 기능은 동작.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # T8 AI Playground — Tencent MPaaS AIGC (OpenAI-compatible) -----------------
    # 단일 endpoint 로 8 공급자 (Claude/GPT/Gemini/Grok/Kimi/GLM/MiniMax/DeepSeek) 호출.
    # 두 가지 인증 모드:
    #   (a) 수동 모드 — tencent_aigc_api_key 직접 주입 (fallback, 디버깅용).
    #   (b) 자동 모드 — tencent_aigc_secret_id/key + subapp_id 로 VOD CreateAigcApiToken
    #       자동 호출 → ApiToken 캐시 (55분 TTL). (a)/(b) 동시 설정 시 (a) 우선.
    tencent_aigc_api_key: str = ""
    tencent_aigc_base_url: str = "https://text-aigc.vod-qcloud.com/v1"
    # 자동 ApiToken 발급 (TC3-HMAC-SHA256, vod.tencentcloudapi.com / CreateAigcApiToken).
    tencent_aigc_subapp_id: str = ""  # 예: "1500033704"
    tencent_aigc_secret_id: str = ""  # 텐센트 클라우드 SecretId
    tencent_aigc_secret_key: str = ""  # 텐센트 클라우드 SecretKey
    tencent_aigc_vod_endpoint: str = "vod.tencentcloudapi.com"
    tencent_aigc_region: str = "ap-seoul"
    # 캐시 만료 (실 ApiToken TTL 1시간 가정, 보수적으로 55분).
    tencent_aigc_token_ttl_seconds: int = 3300

    # T9 신사업유통 텔레그램 자동화 (T9 PRD) ----------------------------------
    # Fernet 마스터 키 — api_id/api_hash 암호화 저장에 사용.
    # 생성: ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``
    # 운영에서 .env 에만 두고, 회전 시엔 키 wrap 후 모든 *_enc 컬럼 재암호화.
    distribution_fernet_key: str | None = None
    # Telethon .session 파일 저장 루트. 권한 0600 강제, 컨테이너 volume mount.
    distribution_telethon_session_dir: str = "/var/lib/distribution/sessions"
    # 대화 생성용 Claude 모델. 톤이 중요하므로 Sonnet 기본 (T9 PRD 6-3).
    distribution_claude_model: str = "claude-sonnet-4-6"
    # 페르소나당 일일 송신 한도 기본값 (DB 컬럼이 우선, 이건 fallback).
    distribution_default_daily_limit: int = 30
    # 신규 페르소나 워밍업 기간 (일). 이 기간엔 송신 빈도 ↓.
    distribution_warmup_days: int = 7
    # 송신 실패 재시도 횟수 (지수 백오프).
    distribution_send_retry_max: int = 3
    # 송신 워커 큐 폴링 간격 (초).
    distribution_worker_poll_interval: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
