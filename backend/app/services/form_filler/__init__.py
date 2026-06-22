"""T5 트랙: 범용 문서 자동 작성기 서비스.

PRD: 업무개선요구사항/PRD/T5_범용문서자동작성기_PRD.md

서비스 모듈 구성 (PRD 7.2, 13.2):
- analyzer: .docx 양식 → markdown → Claude Sonnet 4.6 → 변수 JSON (FR-01)
- mapper: 자료 청크 + 양식 변수 → Claude Sonnet 4.6 → 매핑 JSON (FR-04, NFR-04)
- renderer: 매핑 + 양식 → python-docx 변수 치환 → .docx (FR-06)
- extractor: PDF/DOCX/XLSX/CSV 텍스트 추출 (FR-03, T2 재사용)
- (nas_bridge 는 app.services.nas_search.bridge 로 이동 — 공유 RAG 브릿지)
- prompts: Langfuse 프롬프트 + 시스템 프롬프트 (NFR-04 가드레일 포함)
- guardrails: source_id 검증 + 토큰 정규식 + JSON 스키마 검증 (NFR-04)
- llm_client: Anthropic SDK + Langfuse 트레이스 어댑터

환각 방어 5개 방어선 (NFR-04, 모두 강제):
1. DB CHECK: form_mappings.value NOT NULL → source_id NOT NULL (T5-A 영역)
2. confidence 임계: 0.5 미만은 자동 채움 거부 (mapper.filter_low_confidence)
3. 토큰 검증: 숫자/고유명사가 source_excerpt 안에 있는지 정규식 (guardrails.verify_token_grounding)
4. 검수 강제: status=reviewing → completed만 허용, 직접 completed 차단 (forms.py)
5. 출처 메타 5종 항상 포함: source_id + source_excerpt + llm_confidence + reasoning + variable_key
"""
