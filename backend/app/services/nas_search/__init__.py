"""NAS 자료 검색 모듈 서비스 (v0.6.0 PoC).

구성 요소:
- file_walker: NAS 디렉토리 워크 + 변경 감지
- text_extractor: PDF/DOCX/PPTX 텍스트 추출 + 청크 분할
- embedder: sentence-transformers 기반 텍스트 임베딩
- indexer: 위 3개를 묶는 백그라운드 파이프라인 + 진행률 싱글톤
- summarizer: Claude Haiku 4.5 기반 한국어 키워드 요약 (chunk_index=-2 backfill)
"""
from app.services.nas_search.indexer import (  # noqa: F401
    INDEX_PROGRESS,
    SUMMARY_PROGRESS,
    is_indexing,
    is_summarizing,
    run_indexing,
)
