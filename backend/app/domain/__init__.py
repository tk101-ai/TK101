"""Domain Layer — 외부 의존성 0.

순수 Python. FastAPI / SQLAlchemy / pydantic 등 어떤 외부 라이브러리도 import 금지.

포함:
- entities/: 비즈니스 엔티티 (@dataclass(frozen=True))
- value_objects/: 값 객체
- repositories/: 영속화 인터페이스 (ABC)
- services/: Domain Service 인터페이스
- providers/: 외부 서비스 추상화 (LLM, JWT 등)
- exceptions.py: DomainException 계층
"""
