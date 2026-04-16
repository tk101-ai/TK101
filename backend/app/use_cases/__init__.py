"""Application Layer — Use Cases.

비즈니스 흐름을 오케스트레이션. Domain 인터페이스를 통해
Infrastructure 구현체를 사용 (Dependency Inversion).

Clean Architecture 규칙:
- Import 가능: Domain
- Import 금지: Presentation, Infrastructure 구현체

Sprint 1+ 예정 모듈:
- auth/authenticate_user.py
- auth/refresh_token.py
- user/create_user.py
- user/list_users.py
- ...
"""
