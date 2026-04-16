"""TK101 AI Platform Backend — Clean Architecture.

4 레이어:
    - Presentation (app/api/)
    - Application (app/use_cases/)
    - Domain (app/domain/) — 외부 의존성 0
    - Infrastructure (app/infrastructure/)

의존 방향: Presentation → Application → Domain ← Infrastructure
"""

__version__ = "0.1.0"
