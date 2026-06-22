from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# pool_pre_ping: 배포 후 DB 재시작/유휴로 끊긴 stale 커넥션을 사용 전 핑으로 감지·교체(B2).
# pool_recycle: 30분 이상 묵은 커넥션은 선제 폐기(서버측 idle timeout 회피).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
        except Exception:
            # 예외 발생 시 미커밋 트랜잭션을 롤백해 커넥션을 깨끗한 상태로 반납(J2).
            await session.rollback()
            raise
        # async_session() 컨텍스트 종료 시 세션은 항상 close 된다.
