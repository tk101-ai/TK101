"""요구 기반 문서 생성 (T5 확장).

양식 채우기(form_filler)와 달리, 사용자가 '주제/요구'만 주면 NAS 벡터검색(RAG)으로
회사 자료를 끌어와 LLM이 제안서/계획서/보고서 초안을 구조화 생성한다. 생성 결과는
마크다운 미리보기 + 섹션 구조로 반환하고, 별도 엔드포인트에서 .docx로 렌더한다.

재사용: form_filler.nas_bridge(Qdrant RAG), form_filler.llm_client(call_claude).
"""
from app.services.docgen.docx_builder import build_docx
from app.services.docgen.generator import (
    generate_document,
    regenerate_section,
    render_markdown,
)
from app.services.docgen.pptx_builder import build_pptx

__all__ = [
    "generate_document",
    "regenerate_section",
    "render_markdown",
    "build_docx",
    "build_pptx",
]
