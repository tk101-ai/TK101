"""Infrastructure Layer — 외부 시스템 어댑터.

Domain 인터페이스를 구현:
- database/: SQLAlchemy 세션, ORM 모델
- repositories/: Domain Repository 인터페이스의 SQLAlchemy 구현
- services/: Domain Service 인터페이스 구현 (bcrypt 등)
- providers/: 외부 서비스 어댑터 (Claude, JWT 라이브러리)

Clean Architecture 규칙:
- Import 가능: Domain
- Import 금지: Application, Presentation
"""
