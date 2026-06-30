from pydantic import model_validator
from pydantic_settings import BaseSettings

# JWT 시크릿 최소 길이/금칙값. HS256 서명키가 약하면 토큰 위조가 가능하므로
# 기동 시점에 차단(B1 fail-fast). 운영 값은 .env(JWT_SECRET)로만 주입한다.
_WEAK_JWT_SECRETS = {"", "change-me"}
_MIN_JWT_SECRET_LEN = 16


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tk101:password@localhost:5432/tk101"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    google_youtube_api_key: str | None = None
    # 셀프 회원가입 허용 이메일 도메인(콤마 구분). 이 도메인 외 가입 거부.
    # 빈 문자열이면 셀프 가입 비활성(보수적 기본). 관리자가 정보 보고 승인하는 구조.
    allowed_signup_domains: str = "tk101global.com"
    internal_api_token: str | None = None

    # T1 트랙: 서울시 글로벌 SNS — Meta(Facebook/Instagram) Graph API ----------
    # 시크릿은 .env 에만 주입(commit 절대 금지). 비어 있으면 자동 수집/메트릭 비활성화,
    # 수동 콘텐츠 등록은 토큰 없이도 동작한다 (FALLBACK 모드).
    # 발급: Meta for Developers → 앱 생성 → Graph API 장기 토큰(Page/IG 권한 포함).
    meta_access_token: str = ""  # Page/IG 장기 액세스 토큰
    meta_app_id: str = ""  # Meta 앱 ID (토큰 디버그/재발급용)
    meta_app_secret: str = ""  # Meta 앱 시크릿 (appsecret_proof 서명용)
    # Graph API 버전. 운영 중 신버전 전환 시 .env(META_GRAPH_VERSION)로만 조정.
    # 2026-06-01: 마케팅1팀 Meta 핸드오프 기준 v25.0 (Seoul Korea 페이지 / seoulcity IG).
    meta_graph_version: str = "v25.0"

    # NAS 자료 검색 (v0.6.0 PoC) -------------------------------------------------
    # 운영 환경에서 NAS 마운트 경로. 컨테이너에서 호스트 NAS를 bind mount.
    nas_mount_path: str = "/mnt/nas"
    nas_index_max_file_mb: int = 50
    # 청크는 문자 기반 근사. 토큰 환산 시 약 500 token 수준.
    nas_index_chunk_size: int = 500
    nas_index_chunk_overlap: int = 50

    # NAS 검색 v2 — Qdrant 단일 소스 (feat/nas-qdrant) ---------------------------
    # 레거시 pgvector(nas_text_chunks.embedding) 대신 Qdrant docs_text 컬렉션을
    # 벡터 arm + 키워드 arm 양쪽의 단일 소스로 사용. 인덱싱 파이프라인
    # (/home/ubuntu/tk101-rag) 의 config.py 규약을 그대로 복제한다.
    #
    # 기본값은 컨테이너 내부용(같은 docker 네트워크의 qdrant 서비스).
    # 호스트 직접 실행/dev 검증은 .env(QDRANT_URL=http://localhost:6333)로 override.
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_text: str = "docs_text"
    # 쿼리 임베딩 모델 — 인덱싱과 동일 (Qwen3-Embedding-4B, 2560-dim).
    # 백엔드 CPU(sentence-transformers)에서 기동 시 1회 로드(bf16, ~8GB).
    nas_query_embed_model: str = "Qwen/Qwen3-Embedding-4B"
    nas_query_embed_dim: int = 2560
    # bf16 로드 여부. CPU 메모리 절약용. False면 fp32(정확하나 ~2배 메모리).
    nas_query_embed_bf16: bool = True
    # Qwen3-Embedding 쿼리 instruction 프리픽스 — 쿼리에만 붙인다(문서는 raw).
    # Qwen3는 비대칭 학습(query=instruct, passage=raw)이라 이게 정석이며,
    # 재인덱싱 불필요. 실측상 관련 매칭은 올리고 도메인-무관 노이즈는 떨어뜨려
    # 분리도를 개선한다. 빈 문자열이면 프리픽스 비활성(과거 raw 동작).
    nas_query_instruct: str = (
        "Instruct: Given a web search query, retrieve relevant passages "
        "that answer the query\nQuery: "
    )
    # 벡터-only 후보의 **느슨한 사전 floor**(raw cosine). 진짜 관련도 판정은
    # 리랭크 후 nas_rerank_min_score 가 한다(아래). 이 값은 리랭크 풀에 들어갈
    # 후보를 추리는 용도일 뿐이라 낮게 둔다.
    # 실측(라이브 Qwen3): 정답이 raw cosine 0.55~0.72에 뭉쳐 게이트 0.50과
    # 마진이 얇았고, 0.45~0.49대 정답이 리랭커(0.001~0.978로 변별)에 닿기도 전에
    # 잘렸다. → 사전 floor를 0.35로 낮춰 정답을 리랭커까지 통과시키고, 노이즈
    # 제거는 리랭크 점수 게이트로 넘긴다(이것이 raw cosine보다 변별이 훨씬 큼).
    nas_min_relevance: float = 0.35
    # 키워드 arm: Qdrant payload `text`/`path`에 풀텍스트 인덱스(MatchText)를 만들면
    # (2026-06-23, word 토크나이저) 후보를 **토큰 매칭으로 미리 거른 뒤** 스캔한다.
    # 과거엔 인덱스가 없어 임의 prefix 4000개만 scroll → 코퍼스 0.6%만 봐서 정확
    # 토큰(품번·고유명사·파일명)을 거의 못 잡았다. 인덱스 후엔 전체 코퍼스에서
    # 토큰 포함 문서만 추려 scan_limit 안에서 점수화(정확매칭 복원 + 빨라짐).
    nas_keyword_fulltext: bool = True  # False면 과거 전체 scroll 방식(롤백용)
    # MatchText로 거른 후보를 이 수만큼 scroll 후 토큰 매칭수로 점수화 → doc_id dedup.
    nas_keyword_scan_limit: int = 4000

    # 리랭커(cross-encoder) — 1차 하이브리드 상위 N개를 (쿼리,청크) 직접 채점해
    # 재정렬. bi-encoder cosine + 키워드 0.85 floor 의 변별 약함을 보정한다.
    # CPU 추론(기동 시 워밍업). 끄려면 NAS_RERANK_ENABLED=0.
    nas_rerank_enabled: bool = True
    nas_rerank_model: str = "BAAI/bge-reranker-v2-m3"  # 다국어 KO/ZH/EN
    # 지연/품질 trade-off (CPU 추론, 메모리대역폭 병목이라 스레드론 못 줄임).
    # ⚠️ max_length 256은 품질을 크게 떨어뜨린다 — 규제/제도 문서는 핵심이 청크
    # 뒷부분에 있어 잘리면 관련도를 못 잡는다(실측: 512는 관련문서 0.92로 1위,
    # 256은 그 문서가 탈락+점수 0.46로 폭락). 따라서 **512 유지**하고 지연은
    # top_n으로만 조절한다. 실측(라이브, 워밍업 후): ~0.38s/passage →
    # N12=4.6s / N20=7.6s / N30=12s. 기본 limit=20을 충족하려면 풀이 20은 돼야
    # 하므로(N12면 20개 요청해도 12개만 반환됨) N20 채택(총 ~8s). env로 조절 가능.
    nas_rerank_top_n: int = 20  # 재채점할 상위 후보 수(>= 기본 limit)
    nas_rerank_max_length: int = 512  # 청크 토큰 길이(품질상 절단 금지 권장)
    # 리랭크 **후** 최종 관련도 게이트(cross-encoder sigmoid 점수, 0~1).
    # 이것이 진짜 "없으면 없다" 컷이다 — raw cosine(노이즈 0.46 vs 정답 0.55로
    # 마진 얇음)과 달리 리랭커는 노이즈를 ~0.001, 정답을 0.6~0.98로 분리하므로
    # 이 점수로 게이트하면 정답 보존+노이즈 제거가 깔끔하다.
    # 실측 튜닝(before/after): 0.05면 본문이 약한(엑셀 숫자행 등 H4 영향) 같은
    # 시리즈 정답까지 보존(현대면세점 주간보고 10건)하면서, 무관 질의는 여전히
    # 0건(깊은 노이즈는 rerank ~0.001이라 0.05로도 충분히 컷). 0.10은 H4 영향
    # 문서를 과차단했다. 파일명 임베딩(H4) 적용 후엔 정답 점수가 올라가므로
    # 이 게이트를 더 높일 수 있다. env(NAS_RERANK_MIN_SCORE)로 조절 가능.
    nas_rerank_min_score: float = 0.05

    # 자체 회사문서 부스트 -------------------------------------------------------
    # TK101 자체 자료(회사소개서·제안서·견적 등)는 코퍼스에서 절대 소수다
    # (실측 분포: COMPANY ~수십건 vs MARKETING 고객사 ~수천건). 그래서 "우리 회사
    # 소개" 류 질의에서도 점수상 고객사 소개서에 밀려 묻힌다(운영 확인). 경로에
    # self-company 마커(/COMPANY/)가 있는 청크에 작은 가산 부스트를 줘, 비슷한
    # 점수대에서 자체문서가 앞서게 한다. 강한 관련 고객사 문서를 누를 만큼 크지
    # 않게 보수적으로(가산 ~0.06). 0이면 비활성. 동적 설계상 브랜드명이 아니라
    # 코퍼스의 자체자료 경로 마커로 식별하므로 폴더 추가 시 자동 반영된다.
    nas_self_company_path_marker: str = "/COMPANY/"
    nas_self_company_boost: float = 0.06

    # 부서별 검색 스코핑 (선택 기능) ----------------------------------------------
    # 켜면 일반 사용자는 본인 부서(Qdrant dept)로 한정, 전체검색 허용 역할은 무필터.
    # 사용자 부서 enum(marketing_1/new_business/...)과 Qdrant 문서 dept 라벨
    # (RND/신사업/마케팅본부/경영지원팀)이 다르므로 아래 매핑 dict로 변환한다.
    # 매핑에 없는 사용자 부서는 보수적으로 전체검색(기능을 막지 않기 위함).
    nas_dept_scoping_enabled: bool = False
    # 전체검색이 허용되는 사용자 role 목록(쉼표구분). 기본 admin만.
    nas_full_search_roles: str = "admin"

    @property
    def nas_full_search_role_set(self) -> set[str]:
        return {r.strip() for r in self.nas_full_search_roles.split(",") if r.strip()}

    # 사용자 부서 → Qdrant 문서 dept 라벨(들). 한 사용자 부서가 여러 doc dept를
    # 볼 수 있으면 리스트로(MatchAny).
    # ⚠️ Qdrant 실측 dept 라벨 분포(2026-06-18): 마케팅(≈609k) / RND / 신사업 /
    #    경영지원팀 / 마케팅본부(≈410). 마케팅 코퍼스의 대부분은 '마케팅' 라벨이고
    #    '마케팅본부'는 극소수다. 과거 매핑이 '마케팅본부'만 가리켜, 스코핑을 켜면
    #    마케팅 사용자가 정작 '마케팅' 라벨 문서를 못 보는 문제가 있었다 → 둘 다 포함.
    # 매핑이 없는(=None/누락) 부서는 전체검색으로 폴백한다.
    DOC_DEPT_BY_USER_DEPT: dict[str, list[str]] = {
        "marketing_1": ["마케팅", "마케팅본부"],
        "marketing_2": ["마케팅", "마케팅본부"],
        "new_business": ["신사업"],
        "finance": ["경영지원팀"],
        "new_media": ["마케팅", "마케팅본부"],
        "design": ["마케팅", "마케팅본부"],
        # admin 부서는 전체검색 역할로 처리되므로 매핑 불필요.
    }

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
    # 생성/채움 문서 결과물을 부서별로 NAS에 사본 저장하는 루트 (RW 마운트).
    # 경로 스킴: {루트}/{부서}/{YYYY-MM-DD}/{파일명}. best-effort — 실패해도 다운로드는 정상.
    docwork_nas_output_root: str = "/mnt/nas-rw/문서작업"
    # 단일 양식 업로드 한도 (FR-01).
    form_filler_max_form_mb: int = 50
    # 문서 생성기(docgen) — 디자인/구조 품질 옵션 -------------------------------
    # 구조 설계 모델. 기본 Sonnet 4.6(내용 충분). 더 높은 구조 완성도 원하면 env로
    #   DOCGEN_MODEL=claude-opus-4-8 처럼 토글(비용↑). None이면 form_filler Sonnet.
    docgen_model: str | None = None
    # 브랜드 테마 색(hex). 표지/제목바/표헤더/차트에 사용. env로 회사 색 주입 가능.
    docgen_brand_primary: str = "#16335B"   # 딥 네이비(제목바·표지 배경)
    docgen_brand_accent: str = "#2D7FF9"    # 포인트 블루(강조선·차트)
    docgen_brand_text: str = "#1A2230"      # 본문 텍스트
    docgen_footer_text: str = "TK101"       # 슬라이드/문서 푸터 라벨
    # (선택) 기존 회사 템플릿/로고를 떨어뜨리면 그대로 사용. 없으면 기본 테마로 생성.
    docgen_pptx_template: str | None = None  # .pptx 마스터 템플릿 경로
    docgen_docx_template: str | None = None  # .docx 템플릿 경로
    docgen_logo_path: str | None = None      # 표지/푸터 로고 이미지 경로(png)
    # 자동 검수→재생성 루프(LLM-as-judge 피드백). 초안 생성 후 review_document 로 평가하고,
    # grounded=false 거나 issues 가 있는 섹션을 regenerate_section 으로 다시 쓴다.
    # 기본 OFF — 검수 1회 + 섹션당 재생성 1회씩 추가 LLM 호출이라 비용·지연이 늘어 명시적
    # opt-in 으로 둔다. env(DOCGEN_AUTO_REVIEW=1) 또는 요청 플래그(auto_review=true)로 켠다.
    docgen_auto_review: bool = False
    # 한 번의 자동 루프에서 재생성할 섹션 최대 개수(비용·지연 상한). 점수 낮은 순으로 자른다.
    docgen_auto_review_max_sections: int = 4
    # NAS 검색 쿼리 정제 — 자유지시문(topic)에서 핵심 검색어만 추출해 의미검색 품질↑.
    #   "…자료 찾아서 보고서 써줘" 같은 지시·형식 토큰이 임베딩을 흐리는 문제를 막는다.
    #   저비용 Haiku 1회(temperature=0). 끄면 원본 지시문을 그대로 검색에 쓴다(과거 동작).
    docgen_query_refine_enabled: bool = True
    docgen_query_refine_model: str | None = None  # None이면 form_filler_haiku_model.

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
    # Image/Video 생성 endpoint (international VOD). TC3-HMAC-SHA256 동일 서명.
    # 메모 호출 예시 기준: vod.intl.tencentcloudapi.com / CreateAigcImageTask · CreateAigcVideoTask
    tencent_aigc_vod_intl_endpoint: str = "vod.intl.tencentcloudapi.com"
    # Image-to-Video(i2v)는 MPS(Media Processing Service)의 CreateAigcVideoTask.
    # 공개문서 1041/76487 기준: ImageUrl(top-level, 공개 URL) 입력. VOD가 아님.
    tencent_aigc_mps_intl_endpoint: str = "mps.intl.tencentcloudapi.com"
    tencent_aigc_mps_version: str = "2019-06-12"
    # MPS CreateAigcVideoTask 는 출력 COS 버킷(StoreCosParam)이 **필수**이고, MPS가
    # COS 에 쓰도록 콘솔에서 MPS_QcsRole 역할 승인이 선행돼야 한다. 아래 3개를 채우면
    # i2v create 에 StoreCosParam 을 붙인다. 비어 있으면 i2v 는 명확한 에러로 막는다
    # (출력처 없는 고아 task 생성 방지).
    tencent_aigc_mps_cos_bucket: str = ""  # CosBucketName (예: aigc-1300000000)
    tencent_aigc_mps_cos_region: str = ""  # CosBucketRegion (예: ap-guangzhou)
    tencent_aigc_mps_cos_path: str = "/aigc-video/"  # CosBucketPath
    # 비동기 task 폴링 간격 (초). 너무 짧으면 텐센트 RateLimited.
    tencent_aigc_task_poll_interval: float = 3.0
    # 폴링 최대 대기 시간 (초). 영상은 30~60초 걸릴 수 있어 넉넉히.
    tencent_aigc_task_poll_timeout: int = 300

    # Playground 영속화 ----------------------------------------------------------
    # 텐센트 임시 URL (7일 만료) 을 영구 보관하기 위한 백엔드 디스크 루트.
    # docker-compose 에 volume mount: ``playground_media:/var/lib/playground/media``
    playground_media_root: str = "/var/lib/playground/media"
    # 미디어 보관 기간 (일). 경과분은 정리 대상.
    playground_media_retention_days: int = 30
    # 미디어 자동정리(주기 태스크) 활성화. 기본 OFF — 비가역 하드삭제라 명시적 opt-in.
    # OFF 면 admin 수동 엔드포인트(POST /api/playground/admin/media/cleanup)로만 정리.
    playground_media_autocleanup_enabled: bool = False
    # Playground 로그 — NAS 영구 저장 (RotatingFileHandler, 10MB × 5).
    # 운영 환경에서 NAS RW 마운트 ``/mnt/nas-rw/logs/backend/`` 위에 저장.
    playground_log_path: str = "/mnt/nas-rw/logs/backend/backend.log"

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
    # 예약 송신 백그라운드 워커 활성화 여부.
    # 기본 False — dev/local 에서는 절대 자동 실행되지 않음 (실 텔레그램 송신 방지).
    # 운영에서만 .env 로 True 설정 + Fernet 키 존재 시에만 lifespan 에서 기동.
    distribution_worker_enabled: bool = False
    # 예약 송신 워커 폴링 주기 (초). due 세션/메시지 탐색 간격.
    distribution_worker_poll_sec: int = 15
    # 메시지 첨부 파일 저장 디렉토리 (NAS RW). 운영: ``/mnt/nas-rw/distribution/attachments``.
    # 로컬/개발에선 컨테이너 내부 또는 nas-stub 경로로 override.
    distribution_attachment_dir: str = "/mnt/nas-rw/distribution/attachments"
    # 첨부 1건 최대 크기 (바이트). 200MB. Telethon 자체는 2GB까지 OK.
    # 너무 크면 사내 회선/NAS RW 부담 — 정말 큰 파일은 NAS 공유 링크로 대체 권장.
    distribution_attachment_max_bytes: int = 200 * 1024 * 1024

    # T9 면장(통관신고) 역산 비율 (Priority 4) ----------------------------------
    # 면장(customs declaration)에 기재되는 신고가는 관세 절감 목적으로 실제 가치의
    # 75% 로 신고된다. 실가 역산 공식: actual_price = declared_price / ratio.
    # 0.75 가 표준이지만 거래/품목에 따라 달라질 수 있어 .env 로 조정 가능하게 분리.
    # (예: 다른 비율 적용 시 .env 에 DISTRIBUTION_CUSTOMS_DECLARE_RATIO=0.70)
    distribution_customs_declare_ratio: float = 0.75

    # T9 면장 LLM 추출 (Priority 4) ----------------------------------------------
    # 면장 PDF 양식은 통관사/품목마다 천차만별이라 헤더·정규식 기반 파싱은 항상 깨진다.
    # 텍스트 추출 후 LLM 에 JSON 스키마로 추출 요청 → 양식 변경에 강함.
    # 모델은 form_filler 와 동일 어댑터(call_claude) 사용. 나중에 텐센트 통합 API로
    # 교체할 때는 llm_client 어댑터만 손대면 된다 (호출자는 동일).
    # Haiku 4.5 가 한국어 면장 추출에 충분하고 단가가 낮아 기본값.
    distribution_customs_llm_model: str = "claude-haiku-4-5-20251001"
    # LLM 호출 비활성화 스위치 (.env). True 이면 기존 헤더/정규식 경로만 사용.
    # 키가 없거나 라이브 비용 통제가 필요할 때 즉시 차단 가능.
    distribution_customs_llm_enabled: bool = True
    # LLM 입력 텍스트 상한 (문자). 면장 PDF 1장 ~ 수천자 수준. 비용·지연 방어.
    distribution_customs_llm_max_chars: int = 20000
    # LLM 출력 토큰 상한. 한 PDF 당 10~50건 정도 예상 → 4k 면 충분.
    distribution_customs_llm_max_tokens: int = 4096

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        """기동 시 JWT 시크릿이 약하면(빈값/기본값/너무 짧음) 즉시 중단.
        운영에서 기본 'change-me' 또는 미설정으로 뜨는 것을 막는다(B1)."""
        secret = (self.jwt_secret or "").strip()
        if secret in _WEAK_JWT_SECRETS or len(secret) < _MIN_JWT_SECRET_LEN:
            raise ValueError(
                "JWT_SECRET가 안전하지 않습니다. .env에 16자 이상의 임의 시크릿을 "
                "설정하세요(기본값 'change-me'/빈값/16자 미만 금지)."
            )
        return self


settings = Settings()
