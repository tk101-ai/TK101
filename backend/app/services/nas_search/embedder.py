"""sentence-transformers 기반 텍스트 임베딩.

multilingual-e5-large 사용:
- 1024-dim 출력
- query는 'query: ' prefix, passage는 'passage: ' prefix 권장
- 첫 호출 시 HF Hub에서 가중치 다운로드 (약 2.2GB) — 프로덕션은 미리 워밍업 필요
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: "SentenceTransformer | None" = None
_model_lock = threading.Lock()


def _get_model() -> "SentenceTransformer":
    """전역 싱글톤 모델 lazy load. 멀티스레드 안전."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        logger.info("임베딩 모델 로딩 시작: %s", settings.nas_index_text_model)
        _model = SentenceTransformer(settings.nas_index_text_model)
        logger.info("임베딩 모델 로딩 완료")
        return _model


def _encode(texts: list[str], *, prefix: str) -> "np.ndarray":
    if not texts:
        import numpy as np

        return np.empty((0, 1024), dtype="float32")

    model = _get_model()
    prefixed = [f"{prefix}{t}" for t in texts]
    vectors = model.encode(
        prefixed,
        batch_size=settings.nas_index_batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors


def embed_passages(texts: list[str]) -> "np.ndarray":
    """문서 청크 임베딩. e5는 'passage: ' prefix 필수."""
    return _encode(texts, prefix="passage: ")


def embed_query(text: str) -> "np.ndarray":
    """단일 쿼리 임베딩. e5는 'query: ' prefix 필수. shape (1024,)."""
    vectors = _encode([text], prefix="query: ")
    return vectors[0]
