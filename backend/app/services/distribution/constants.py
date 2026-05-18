"""신사업유통 모듈 상수 (T9 Phase F).

회사 코드 동기화 위치:
- Backend: 이 파일 ``DISTRIBUTION_COMPANIES`` 튜플
- Frontend (Agent D): ``DISTRIBUTION_COMPANIES`` 배열

새 회사 추가 시 양쪽 같이 수정 + 알파벳 정렬 유지 X (관리 순서로).
"""
from __future__ import annotations

from typing import Final

# 4 회사 코드 — Agent D 의 frontend `DISTRIBUTION_COMPANIES` 와 동기화 필수.
# 새 회사 추가 시 양쪽 같이 수정.
DISTRIBUTION_COMPANIES: Final[tuple[str, ...]] = (
    "TK101",
    "래더엑스",
    "뉴테인핏",
    "SYBT",
)

# 자동 추출/명시 모두 실패한 경우의 fallback. 현재 단일 회사 운영 가정.
DEFAULT_COMPANY: Final[str] = "래더엑스"
