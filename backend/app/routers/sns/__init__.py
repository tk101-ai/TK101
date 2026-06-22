"""SNS 라우터 패키지.

기존 단일 파일 `routers/sns.py`(2173줄)를 도메인별 모듈로 분할했다. 공개 진입점은
그대로 유지된다 — `from app.routers.sns import router`(및 `internal_router`)가
동일한 객체를 노출하므로 `main.py` 는 변경 불필요.

서브모듈 import 가 곧 라우트 등록이다(각 모듈이 `_common.router` /
`_common.internal_router` 에 엔드포인트를 데코레이터로 붙인다). 무거운 비 HTTP 로직
(SQL 집계·엑셀 피벗·수집 오케스트레이션)은 `services/sns_stats.py`,
`services/sns_collection.py`, 기존 `services/sns_export.py` 로 분리했다.
"""

from ._common import internal_router, router

# 아래 import 들이 router/internal_router 에 엔드포인트를 등록한다(부수효과).
from . import accounts  # noqa: E402,F401  계정 CRUD + meta/whoami
from . import posts  # noqa: E402,F401  게시물·스냅샷·수동콘텐츠·초기화
from . import stats  # noqa: E402,F401  통계 위젯
from . import export  # noqa: E402,F401  엑셀 내보내기
from . import collection  # noqa: E402,F401  ingest/collect/메트릭/전체갱신
from . import comments  # noqa: E402,F401  댓글 수집·분석·번역
from . import internal as _internal  # noqa: E402,F401  내부 cron 라우터
from . import importers  # noqa: E402,F401  엑셀 임포트

__all__ = ["router", "internal_router"]
