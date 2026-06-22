"""문서 작업(Docwork) 공유 코어 — 향후 출처 레이어·잡 비용·검수·렌더를 담는다.

생성(docgen) / 채우기(form_filler) 두 엔진이 공유하는 docwork 전용 코드 위치.
앱 전역 인프라(llm_client→services/llm/client, nas_bridge→services/nas_search/bridge)는
여기가 아니라 각 중립 패키지에 둔다. 설계: docs/PRD_DOCWORK_UNIFY_2026-06-22.md
"""
