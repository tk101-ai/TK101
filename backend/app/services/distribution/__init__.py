"""신사업유통 텔레그램 대화 자동화 서비스 (T9 PRD).

서브모듈:
- encryption: api_id/api_hash Fernet 암복호화.
- bl_parser: 엑셀 BL/면장 파서 (Day 1 후반).
- scenario_engine: 시나리오 → Claude 프롬프트 변환 (Day 2).
- conversation_generator: Claude 호출 + JSON 응답 검증 (Day 2~3).
- persona_manager: 페르소나 CRUD + Telethon 세션 라이프사이클 (Day 3).
- telegram_worker: 송신 큐 폴링 + Telethon 송신 (Day 4).
"""
