"""NAS 자료 검색 모듈 서비스.

검색 코퍼스는 Qdrant(Qwen3 2560-dim) 단일 소스이며 외부 파이프라인(tk101-rag)이
적재한다. 백엔드는 query_embedder 로 쿼리만 임베딩해 qdrant_search 로 조회한다.

구성 요소:
- query_embedder: Qwen3 쿼리 임베딩 (검색/문서작성 공용)
- qdrant_search: Qdrant vector/keyword arm + 코퍼스 통계
- hybrid / reranker / romanize: 융합·리랭크·로마자 보조
- indexer: 인앱 인덱싱 진행률 싱글톤(legacy, 항상 idle — 상태 API 호환용)
"""
from app.services.nas_search.indexer import (  # noqa: F401
    INDEX_PROGRESS,
    SUMMARY_PROGRESS,
    is_indexing,
    is_summarizing,
)
