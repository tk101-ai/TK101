"""NAS 자료 검색 모듈 서비스 (v0.6.0 PoC).

구성 요소:
- file_walker: NAS 디렉토리 워크 + 변경 감지
- text_extractor: PDF/DOCX/PPTX 텍스트 추출 + 청크 분할
- embedder: sentence-transformers 기반 텍스트 임베딩
- indexer: 위 3개를 묶는 백그라운드 파이프라인 + 진행률 싱글톤
"""
from app.services.nas_search.indexer import (  # noqa: F401
    INDEX_PROGRESS,
    is_indexing,
    run_indexing,
)
