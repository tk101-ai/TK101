"""Qwen3-Embedding-4B 기반 쿼리 임베딩 (NAS 검색 v2 — Qdrant 단일 소스).

인덱싱 파이프라인(/home/ubuntu/tk101-rag)은 문서(passage)를 vLLM에서
**raw 텍스트**(prefix 없음)로 임베딩해 Qdrant docs_text(2560-dim, cosine)에
적재한다. Qwen3-Embedding은 query/passage 비대칭 사용이 정석이므로, 문서는
raw 그대로 두고 **쿼리에만** instruction 프리픽스를 붙여 인코딩한다(아래 참조).

운영 메모:
- sentence-transformers로 백엔드 CPU에서 추론. 기동 시 1회 로드(싱글톤).
  bf16 권장(~8GB). 실측 ~0.8s/쿼리 허용.
- embedder.py(multilingual-e5)의 lazy-load 싱글톤 패턴을 복제했다.
- 쿼리 instruction 프리픽스(settings.nas_query_instruct)를 쿼리에만 붙인다.
  Qwen3-Embedding은 비대칭 학습(query=instruct, passage=raw)이라 이것이 정석이며,
  문서는 prefix 없이 적재된 그대로 두면 된다(재인덱싱 불필요). 실측상 관련 매칭은
  올리고 도메인-무관 노이즈는 떨어뜨려 nas_min_relevance 게이트의 분리도를 높인다.
  프리픽스를 끄려면 nas_query_instruct를 빈 문자열로 두면 과거 raw 동작이 된다.
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

    Qwen3 권장대로 쿼리에 instruction 프리픽스(settings.nas_query_instruct)를
    붙여 인코딩한다(문서는 raw로 적재됨 — 비대칭 사용). cosine 정합을 위해
    normalize한다(Qdrant 컬렉션 distance=Cosine). 차원이 기대와 다르면 즉시
    에러(스키마 불일치 조기 발견 — embed.py 규약 동일).
    """
    model = _get_model()
    vec = model.encode(
        settings.nas_query_instruct + text,
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


def embed_queries(texts: list[str]) -> list[list[float]]:
    """여러 쿼리를 한 번에 임베딩(배치). embed_query 와 동일 규약(prefix+normalize).

    변수별 병렬 검색처럼 N개 쿼리를 임베딩할 때, 단건 N회보다 1회 배치가 훨씬 빠르다.
    """
    if not texts:
        return []
    model = _get_model()
    vecs = model.encode(
        [settings.nas_query_instruct + t for t in texts],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def warmup() -> None:
    """기동 시 모델 미리 로드(첫 쿼리 지연 제거용). lifespan에서 호출 권장."""
    _get_model()
