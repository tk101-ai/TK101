"""T5 트랙: 범용 문서 자동 작성기 라우터 (PRD T5_범용문서자동작성기 7.3).

기존 단일 파일 forms.py(1350줄)를 동작 동일하게 분할한 패키지.
공개 진입점은 그대로 `app.routers.forms.router` 이며, main.py 는 변경 없이 동작한다.

| 메서드 | 경로                                          | 설명 (FR)                       | 모듈      |
|--------|-----------------------------------------------|---------------------------------|-----------|
| POST   | /api/forms/templates/analyze                  | 양식 업로드 + 자동 분석 (FR-01) | templates |
| GET    | /api/forms/templates                          | 라이브러리 목록 (FR-07)         | templates |
| GET    | /api/forms/templates/{id}                     | 양식 + 변수                     | templates |
| PATCH  | /api/forms/templates/{id}                     | 변수 라벨 수정 (FR-02)          | templates |
| DELETE | /api/forms/templates/{id}                     | soft delete                     | templates |
| POST   | /api/forms/jobs                               | 작성 잡 생성                    | jobs      |
| GET    | /api/forms/jobs/{id}                          | 잡 상태 + 매핑 + 출처           | jobs      |
| POST   | /api/forms/jobs/{id}/sources/upload           | 사용자 자료 업로드 (FR-03)      | jobs      |
| POST   | /api/forms/jobs/{id}/sources/nas              | NAS 자료 추가 (FR-03)           | jobs      |
| POST   | /api/forms/jobs/{id}/run_mapping              | 매핑 실행 (FR-04, 출처 강제)    | jobs      |
| PATCH  | /api/forms/jobs/{id}/mappings/{key}           | 매핑 수동 수정 (FR-05/FR-08)    | jobs      |
| POST   | /api/forms/jobs/{id}/regenerate               | 단일 변수 재생성 (Haiku)        | jobs      |
| POST   | /api/forms/jobs/{id}/render                   | .docx 출력 (FR-06)              | jobs      |
| GET    | /api/forms/jobs/{id}/download                 | .docx 다운로드                  | jobs      |
| GET    | /api/forms/jobs/{id}/revisions                | 변경 이력 (FR-08)               | jobs      |
| POST   | /api/forms/cleanup                            | 30일 경과 자료 hard delete      | jobs      |

NFR-04 환각 방어 5개 방어선 적용 위치:
- #1 DB CHECK form_mappings.value/source_id: alembic 007 (T5-A)
- #2 confidence 임계: services.form_filler.guardrails.filter_low_confidence
- #3 토큰 grounding: services.form_filler.guardrails.verify_token_grounding
- #4 검수 강제 status flow: services.form_filler.persistence.enforce_status_transition
- #5 출처 메타 5종: services.form_filler.mapper.MappingResult 강제
"""
from __future__ import annotations

from fastapi import APIRouter

from .jobs import router as jobs_router
from .templates import router as templates_router

# 공개 진입점 — main.py 가 `forms.router` 로 include 한다.
# 서브라우터가 prefix(/api/forms)·tags·모듈 권한 의존성을 모두 보유하므로
# 부모는 prefix 없이 묶기만 한다(경로/의존성 동일).
router = APIRouter()
router.include_router(templates_router)
router.include_router(jobs_router)

__all__ = ["router"]
