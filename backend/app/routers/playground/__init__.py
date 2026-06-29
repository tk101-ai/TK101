"""AI Playground 라우터 (패키지).

엔드포인트 (요약):
| 메서드 | 경로                                            | 권한          | 설명                       |
|--------|-------------------------------------------------|---------------|----------------------------|
| GET    | /api/playground/providers                       | 로그인        | LLM provider/모델 chip     |
| GET    | /api/playground/media-models                    | 로그인        | 이미지/영상 모델 카탈로그  |
| POST   | /api/playground/sessions                        | 로그인        | 빈 세션 생성               |
| GET    | /api/playground/sessions                        | 로그인        | 본인 세션 목록             |
| GET    | /api/playground/sessions/{id}/messages          | 로그인 (본인) | 세션 메시지 전체           |
| DELETE | /api/playground/sessions/{id}                   | 로그인 (본인) | 세션 hard delete           |
| POST   | /api/playground/chat                            | 로그인        | SSE 스트리밍 채팅          |
| POST   | /api/playground/image                           | 로그인        | 이미지 task 생성           |
| POST   | /api/playground/video                           | 로그인        | 영상 task 생성             |
| GET    | /api/playground/tasks/{kind}/{task_id}          | 로그인        | 미디어 task 폴링           |
| GET    | /api/playground/media                           | 로그인 (본인) | 본인 미디어 목록 (보관함)  |
| GET    | /api/playground/media/shared                    | 로그인        | 공유 갤러리 (전체 공유분)  |
| PATCH  | /api/playground/media/{id}/share                | 로그인 (본인) | 공유 on/off 토글           |
| DELETE | /api/playground/media/{id}                      | 로그인 (본인) | 미디어 삭제 (row+파일)     |
| GET    | /api/playground/media/{id}/file                 | 본인/공유     | 미디어 파일 서빙           |
| GET    | /api/playground/admin/usage                     | **admin**     | 모델별/사용자별 사용량     |
| POST   | /api/playground/admin/media/cleanup             | **admin**     | 보존기간 경과 미디어 정리  |

2026-05-19 변경:
- admin only 라우터 의존성 제거 → 일반 사용자가 사용은 가능, 통계는 admin 전용.
- 이미지/영상 task 는 생성 시점에 playground_media row 만들고 폴링 시 업데이트.
- 폴링이 succeeded 받으면 텐센트 임시 URL 을 백엔드 디스크로 다운로드 + cost_usd 계산.
- 단가표 적용 (services/playground/pricing.py).

2026-06-22 리팩토링:
- 단일 1412줄 ``playground.py`` 를 도메인별 모듈로 분할 (동작 동일).
  meta / sessions(+quota) / attachments / chat / media_gen / media_library / admin.
- 무거운 채팅 스트리밍 오케스트레이션은 ``services/playground/chat_orchestrator.py`` 로 추출.
- 공개 진입점은 그대로: ``from app.routers.playground import router``.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    admin,
    attachments,
    chat,
    media_gen,
    media_library,
    meta,
    sessions,
)
from ._common import ROUTER_KWARGS

router = APIRouter(**ROUTER_KWARGS)

# include 순서는 기존 단일 파일의 엔드포인트 등록 순서를 보존한다
# (경로 충돌 우선순위 동일성 유지).
router.include_router(meta.router)
router.include_router(sessions.router)
router.include_router(attachments.router)
router.include_router(chat.router)
router.include_router(media_gen.router)
router.include_router(media_library.router)
router.include_router(admin.router)

__all__ = ["router"]
