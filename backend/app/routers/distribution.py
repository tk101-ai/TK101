"""신사업유통 텔레그램 대화 자동화 라우터 (T9 PRD Phase A).

Phase A 엔드포인트 (구현 완료):
| 메서드 | 경로                                          | 설명                       |
|--------|-----------------------------------------------|----------------------------|
| GET    | /api/distribution/personas                    | 페르소나 목록              |
| POST   | /api/distribution/personas                    | 새 페르소나 등록 + 암호화  |
| PATCH  | /api/distribution/personas/{id}               | 페르소나 부분 수정         |
| DELETE /api/distribution/personas/{id}        | 페르소나 삭제 (세션도 삭제)|
| POST   | /api/distribution/personas/{id}/logout        | 세션 파일 삭제 + 플래그 클리어 |
| POST   | /api/distribution/personas/{id}/login-init    | SMS 코드 발송              |
| POST   | /api/distribution/personas/{id}/verify-code   | SMS 코드 + (선택) 2FA 검증 |
| GET    | /api/distribution/health                      | 모듈 헬스체크              |

Phase B~E (예정): scenarios CRUD, BL upload, generate, sessions review, send-log.

권한: 라우터 전체 ``require_admin``. 세부 작업별 분리는 Phase D 에서.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.schemas.distribution import (
    PersonaCreate,
    PersonaOut,
    PersonaUpdate,
    PersonaVerifyCode,
)
from app.services.distribution import login_manager, persona_service
from app.services.distribution.encryption import EncryptionError

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, str]:
    """T9 모듈 헬스체크. 라우터 등록 검증용."""
    return {"status": "ok", "module": "distribution", "phase": "A"}


# ---------------------------------------------------------------------------
# Persona CRUD
# ---------------------------------------------------------------------------


@router.get("/personas")
async def list_personas(
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[PersonaOut]]:
    """전체 페르소나 목록 (account_label 알파벳 순)."""
    personas = await persona_service.list_personas(db)
    return {"personas": [persona_service.to_out(p) for p in personas]}


@router.post("/personas", status_code=status.HTTP_201_CREATED)
async def create_persona(
    payload: PersonaCreate,
    db: AsyncSession = Depends(get_db),
) -> PersonaOut:
    """새 페르소나 등록.

    Errors:
    - 409: 중복 account_label / phone (UNIQUE 제약).
    - 503: Fernet 키 미설정 (.env DISTRIBUTION_FERNET_KEY 필요).
    """
    try:
        persona = await persona_service.create_persona(db, payload)
    except EncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="중복된 account_label 또는 telegram_phone 입니다.",
        ) from exc
    return persona_service.to_out(persona)


@router.patch("/personas/{persona_id}")
async def update_persona(
    persona_id: UUID,
    payload: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
) -> PersonaOut:
    """페르소나 부분 수정 (display_name, tone_profile, daily_msg_limit, active, warmup_until)."""
    persona = await persona_service.update_persona(db, persona_id, payload)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    return persona_service.to_out(persona)


@router.delete("/personas/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """페르소나 hard delete + 세션 파일 삭제. 관련 messages/sessions 는 RESTRICT FK 로 보호 (수동 정리)."""
    ok = await persona_service.delete_persona(db, persona_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/personas/{persona_id}/logout")
async def logout_persona(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PersonaOut:
    """세션 파일 삭제 + telegram_user_id/session_path 클리어. 자격증명은 보존."""
    persona = await persona_service.logout_persona(db, persona_id)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    return persona_service.to_out(persona)


# ---------------------------------------------------------------------------
# Telethon 로그인 (SMS 2단계)
# ---------------------------------------------------------------------------


@router.post("/personas/{persona_id}/login-init")
async def login_init(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """SMS 인증 코드 발송 트리거.

    Telethon 클라이언트는 백엔드 메모리에 5분 TTL 로 보관 → verify-code 에서 재사용.

    Returns:
        ``{"phone_code_hash": "...", "sent_to_phone_masked": "+8210***2329"}``
    """
    persona = await persona_service.get_persona(db, persona_id)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    try:
        return await login_manager.request_code(persona)
    except ValueError as exc:
        # 자격증명 미설정.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except EncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        # "이미 로그인됨" 또는 Telethon 측 오류.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        # 내부 예외 상세는 서버 로그에만. 클라이언트엔 고정 메시지 (Telethon 내부정보 유출 방지).
        logger.exception("login-init 예외 — persona=%s", persona_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SMS 발송 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
        ) from exc


@router.post("/personas/{persona_id}/verify-code")
async def verify_code(
    persona_id: UUID,
    payload: PersonaVerifyCode,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """SMS 코드 + (선택) 2FA 비밀번호 검증.

    2FA 활성인데 password 미입력 시 422 반환 → UI 가 비밀번호 입력 후 재호출.
    SMS 코드 잘못이면 400.
    """
    persona = await persona_service.get_persona(db, persona_id)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    try:
        return await login_manager.verify_code(
            persona,
            db,
            code=payload.code,
            password=payload.password,
        )
    except login_manager.LoginPasswordRequired as exc:
        # UI 가 비밀번호 추가 입력 후 같은 hash 로 재시도해야 함.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except login_manager.LoginCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except login_manager.LoginExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail=str(exc)
        ) from exc
    except EncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        # 내부 예외 상세는 서버 로그에만. 클라이언트엔 고정 메시지.
        logger.exception("verify-code 예외 — persona=%s", persona_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SMS 검증 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
        ) from exc
