"""pytest 전역 fixtures.

Sprint 1+에서 확장:
- DB 트랜잭션 롤백 fixture
- 테스트용 FastAPI TestClient
- 인증된 사용자 fixture
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI TestClient."""
    with TestClient(app) as c:
        yield c
