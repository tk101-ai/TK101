"""SQLAlchemy async 세션 팩토리.

Design Ref: §9.4 Infrastructure — database/session.py
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Async 엔진 — 앱 수명주기 동안 단일 인스턴스
engine = create_async_engine(
    settings.database_url,
    echo=not settings.is_production,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session 팩토리
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """모든 SQLAlchemy ORM 모델의 공통 베이스.

    Alembic이 이 Base.metadata를 타겟으로 autogenerate 실행.
    """


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends용 세션 제너레이터.

    요청당 1 세션. 예외 발생 시 롤백, 정상 종료 시 커밋.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
