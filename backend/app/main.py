from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
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
    distribution_dashboard,
    distribution_generate_v2,
    distribution_scenarios,
    distribution_sessions,
    distribution_triggers,
    forms,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


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


@app.get("/health")
async def health():
    return {"status": "ok"}
