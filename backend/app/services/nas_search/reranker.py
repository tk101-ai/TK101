"""NAS 검색 리랭커 (cross-encoder) — 1차 하이브리드 결과 상위 후보 재정렬.

bi-encoder(임베딩) cosine 은 (쿼리,문서)를 따로 인코딩해 빠르지만, 다중어
질의에서 키워드만 겹쳐도 비슷한 점수가 나와 변별이 약하다(키워드 강매칭은
0.85 floor 로 더 뭉친다). cross-encoder 는 (쿼리,문서)를 함께 입력해 관련도를
직접 채점하므로 상위 후보 재정렬에 강하다.

운영 메모:
- BAAI/bge-reranker-v2-m3 (다국어 KO/ZH/EN, 568M). CPU 추론, 기동 시 워밍업.
- predict()는 relevance logit → sigmoid 로 0~1 정규화해 표시 점수로 쓴다.
- query_embedder 의 lazy 싱글톤 패턴을 복제(첫 호출 1회 로드, 스레드 안전).
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

_model: "CrossEncoder | None" = None
_lock = threading.Lock()


def _get_model() -> "CrossEncoder":
    """전역 싱글톤 리랭커 lazy load. 멀티스레드 안전."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import CrossEncoder

        logger.info("리랭커 모델 로딩 시작: %s", settings.nas_rerank_model)
        _model = CrossEncoder(
            settings.nas_rerank_model,
            max_length=settings.nas_rerank_max_length,
            device="cpu",
        )
        logger.info("리랭커 모델 로딩 완료")
        return _model


def rerank(query: str, passages: list[str]) -> list[float]:
    """(query, passage) 각 쌍의 관련도 0~1 점수. passages 순서 보존.

    sentence-transformers CrossEncoder 는 단일 라벨 모델에 기본 sigmoid 활성화를
    적용하므로 predict() 가 이미 0~1 확률을 돌려준다(추가 sigmoid 금지 — 이중적용
    하면 무관 0.0이 0.5로 뭉개진다). 실측: 관련 0.77~0.80 · 무관 0.00.
    """
    if not passages:
        return []
    model = _get_model()
    raw = model.predict(
        [(query, p) for p in passages],
        show_progress_bar=False,
    )
    return [float(s) for s in raw]


def warmup() -> None:
    """기동 시 모델 로드 + 더미 추론 1회로 가중치를 RAM 에 페이지인.

    임베더와 동일 — _get_model() 만으론 mmap 매핑만 되어 첫 실제 쿼리가 느리다.
    """
    rerank("워밍업", ["워밍업 문서"])
