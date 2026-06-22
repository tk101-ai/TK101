"""인덱싱 진행률 싱글톤.

검색 코퍼스는 외부 파이프라인(tk101-rag → Qdrant/Qwen3)이 적재한다. 과거 인앱 인덱싱
파이프라인(walker → extractor → e5 embed → pgvector nas_text_chunks)은 검색 미반영
dead code였고 032 마이그레이션에서 pgvector 테이블과 함께 제거됨.

여기 남은 IndexProgress 싱글톤은 라우터의 /index/status, /index/summary_status 가
상태 헤더(프론트)에 idle 상태를 응답하기 위한 in-memory 객체일 뿐이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class IndexProgress:
    """진행률 싱글톤. 라우터에서 그대로 직렬화해서 클라이언트에 노출."""

    running: bool = False
    processed: int = 0
    total: int = 0
    current_path: str | None = None
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    failures: list[str] = field(default_factory=list)

    def reset(self, total: int) -> None:
        self.running = True
        self.processed = 0
        self.total = total
        self.current_path = None
        self.errors = 0
        self.started_at = datetime.now(tz=timezone.utc)
        self.finished_at = None
        self.last_error = None
        self.failures = []

    def finish(self) -> None:
        self.running = False
        self.current_path = None
        self.finished_at = datetime.now(tz=timezone.utc)


# 모듈 전역 싱글톤. 인앱 인덱싱은 비활성이라 항상 idle로 유지된다.
INDEX_PROGRESS = IndexProgress()
SUMMARY_PROGRESS = IndexProgress()


def is_indexing() -> bool:
    return INDEX_PROGRESS.running


def is_summarizing() -> bool:
    return SUMMARY_PROGRESS.running
