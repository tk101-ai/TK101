"""Qwen3-Embedding-4B 기반 쿼리 임베딩 (NAS 검색 v2 — Qdrant 단일 소스).

인덱싱 파이프라인(/home/ubuntu/tk101-rag)은 문서(passage)를 vLLM에서
**raw 텍스트**(prefix 없음)로 임베딩해 Qdrant docs_text(2560-dim, cosine)에
적재한다. 코사인 정합을 위해 백엔드 쿼리 임베딩도 **동일 규약**으로 맞춘다:
prefix 없는 raw 텍스트를 그대로 인코딩한다.

운영 메모:
- sentence-transformers로 백엔드 CPU에서 추론. 기동 시 1회 로드(싱글톤).
  bf16 권장(~8GB). 실측 ~0.8s/쿼리 허용.
- embedder.py(multilingual-e5)의 lazy-load 싱글톤 패턴을 복제했다.
- (잠재적 품질 개선) Qwen3는 query에 instruct prefix
    "Instruct: Given a web search query, retrieve relevant passages ...\nQuery: "
  를 붙이면 retrieval 품질이 오를 수 있다. 다만 인덱싱(retriever.py)이 prefix
  없이 raw로 임베딩하므로, 1차 구현은 retriever.py와 **동일하게 prefix 없이** 간다.
  prefix 도입은 문서·쿼리 양쪽 동시 변경이 필요해 통합 단계 과제로 남긴다.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: "SentenceTransformer | None" = None
_model_lock = threading.Lock()


def _get_model() -> "SentenceTransformer":
    """전역 싱글톤 모델 lazy load. 멀티스레드 안전(embedder.py 패턴 복제).

    첫 호출 시 HF Hub에서 가중치 다운로드(약 8GB). 운영에서는 모델을 컨테이너에
    미리 반입하거나 lifespan에서 워밍업해 첫 쿼리 지연을 흡수하는 것을 권장한다.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer

        model_kwargs: dict = {}
        if settings.nas_query_embed_bf16:
            # CPU 메모리 절약. torch import는 sentence-transformers 의존성.
            import torch

            model_kwargs["torch_dtype"] = torch.bfloat16

        logger.info(
            "NAS 쿼리 임베딩 모델 로딩 시작: %s (bf16=%s)",
            settings.nas_query_embed_model,
            settings.nas_query_embed_bf16,
        )
        _model = SentenceTransformer(
            settings.nas_query_embed_model,
            device="cpu",
            model_kwargs=model_kwargs or None,
        )
        logger.info("NAS 쿼리 임베딩 모델 로딩 완료")
        return _model


def embed_query(text: str) -> list[float]:
    """단일 쿼리 → 2560-dim 임베딩(list[float]).

    인덱싱과 동일하게 prefix 없는 raw 텍스트를 인코딩하고 cosine 정합을 위해
    normalize한다(Qdrant 컬렉션 distance=Cosine). 차원이 기대와 다르면 즉시
    에러(스키마 불일치 조기 발견 — embed.py 규약 동일).
    """
    model = _get_model()
    vec = model.encode(
        text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    out = vec.tolist()
    if len(out) != settings.nas_query_embed_dim:
        raise ValueError(
            f"쿼리 임베딩 차원 {len(out)} != nas_query_embed_dim "
            f"{settings.nas_query_embed_dim}. 모델/컬렉션 정합 확인 필요."
        )
    return out


def warmup() -> None:
    """기동 시 모델 미리 로드(첫 쿼리 지연 제거용). lifespan에서 호출 권장."""
    _get_model()
