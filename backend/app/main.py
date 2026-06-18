import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_setup import setup_logging
from app.services.distribution.send_worker import run_send_worker
from app.routers import (
    accounts,
    attachments,
    auth,
    balance_snapshots,
    bank_import,
    categories,
    counterparts,
    distribution,
    distribution_analytics,
    distribution_customs,
    distribution_dashboard,
    distribution_generate_v2,
    distribution_scenarios,
    distribution_sessions,
    distribution_settlement,
    distribution_triggers,
    docgen,
    forms,
    grants,
    matching,
    nas_search,
    playground,
    review_translation,
    sns,
    tax_invoices,
    transactions,
    upload_history,
    uploads,
    users,
)


logger = logging.getLogger(__name__)


def _should_start_send_worker() -> bool:
    """예약 송신 워커 기동 조건.

    - distribution_worker_enabled=True (기본 False — dev/local 자동 실행 방지).
    - Fernet 키 존재 (없으면 자격증명 복호화 불가 → 워커 무의미).
    둘 다 만족할 때만 백그라운드 태스크 기동.
    """
    if not settings.distribution_worker_enabled:
        return False
    if not settings.distribution_fernet_key:
        logger.warning(
            "distribution_worker_enabled=True 이지만 Fernet 키 미설정 — 워커 미기동"
        )
        return False
    return True


async def _warmup_nas_query_embedder() -> None:
    """NAS 검색 v2 쿼리 임베딩 모델(Qwen3-Embedding-4B, ~8GB bf16) 사전 로드.

    첫 쿼리 지연(모델 로드 + 가중치 디스크 read) 흡수용. 모델은 동기 CPU 로드라
    이벤트 루프를 막지 않도록 스레드에서 돌린다. 실패해도(메모리 부족·캐시 미스 등)
    기동은 계속되며, 첫 쿼리 시 lazy load로 재시도된다.
    """
    from app.services.nas_search import query_embedder

    try:
        await asyncio.to_thread(query_embedder.warmup)
        logger.info("NAS 쿼리 임베딩 모델 워밍업 완료")
    except Exception:  # noqa: BLE001
        logger.exception("NAS 쿼리 임베딩 모델 워밍업 실패 — 첫 쿼리 시 lazy load로 재시도")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # 부서→모듈 grant 캐시 로드(DB → 메모리). 인가가 이 캐시를 읽음.
    from app.modules.registry import load_grants_cache

    try:
        await load_grants_cache()
        logger.info("부서-모듈 grant 캐시 로드 완료")
    except Exception:
        logger.exception("grant 캐시 로드 실패 — 하드코딩 매핑으로 폴백")
    # NAS 검색 v2 쿼리 임베딩 모델 워밍업(백그라운드 — 기동을 막지 않음).
    warmup_task = asyncio.create_task(_warmup_nas_query_embedder())
    worker_task: asyncio.Task | None = None
    stop_event = asyncio.Event()
    if _should_start_send_worker():
        worker_task = asyncio.create_task(run_send_worker(stop_event))
        logger.info("distribution 예약 송신 워커 기동")
    try:
        yield
    finally:
        if not warmup_task.done():
            warmup_task.cancel()
            try:
                await warmup_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if worker_task is not None:
            stop_event.set()
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            logger.info("distribution 예약 송신 워커 정지 완료")


app = FastAPI(title="TK101 AI Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(grants.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
# attachments 는 prefix=/api/transactions 공유. 경로별 매칭이므로 충돌 없음.
app.include_router(attachments.router)
app.include_router(uploads.router)
app.include_router(matching.router)
app.include_router(tax_invoices.router)
app.include_router(sns.router)
app.include_router(sns.internal_router)
app.include_router(nas_search.router)
app.include_router(forms.router)
app.include_router(docgen.router)
app.include_router(review_translation.router)
# Wave 2 재무 모듈 신규 라우터
app.include_router(bank_import.router)
app.include_router(categories.router)
app.include_router(counterparts.router)
app.include_router(upload_history.router)
app.include_router(balance_snapshots.router)
# T8 트랙: AI Playground (Phase 1 — Claude 채팅 SSE 스트리밍, admin only).
app.include_router(playground.router)
# T9 트랙: 신사업유통 텔레그램 대화 자동화.
app.include_router(distribution.router)
# T9 Phase C: 세션 검수·송신. prefix 동일하지만 경로별 매칭이라 충돌 없음.
app.include_router(distribution_sessions.router)
# T9 Phase D: fingerprint + 트리거 일자 검사.
app.include_router(distribution_triggers.router)
# T9 Phase E-2: 시나리오 조회 + 커스텀 생성 트리거 (모달용).
app.include_router(distribution_scenarios.router)
app.include_router(distribution_generate_v2.router)
# T9 Phase E-1: 대시보드 집계 (KPI/추이/분포).
app.include_router(distribution_dashboard.router)
# T9 Phase E-4: 분석 페이지 (비용/송신통계/메시지검색).
app.include_router(distribution_analytics.router)
# T9 Phase F-C: 정산 페이지 (엑셀 기반 자금 흐름 — 매입/입금요청/실입금/외상잔고).
app.include_router(distribution_settlement.router)
# Priority 4: 면장(통관신고) 데이터 수집. 신고가 → 실가 75% 역산.
app.include_router(distribution_customs.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
