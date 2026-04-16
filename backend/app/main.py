"""FastAPI 애플리케이션 진입점.

Design Ref: §9.4 Feature Module Structure — Presentation Layer
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routers import health
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 수명주기 관리 (startup/shutdown)."""
    # Startup — DB 연결 검증 등 (도메인 모듈 추가 시 확장)
    yield
    # Shutdown — 커넥션 풀 정리 등


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리."""
    settings = get_settings()

    app = FastAPI(
        title="TK101 AI Platform API",
        description="사내 40명 대상 AI 업무 자동화 플랫폼 백엔드",
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    app.include_router(health.router, tags=["health"])
    # Sprint 1+에서 아래 라우터들이 추가됨:
    # app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    # app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    # app.include_router(departments.router, prefix="/api/v1/departments", tags=["departments"])
    # app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])

    return app


app = create_app()
