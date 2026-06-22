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

권한 (T9 라우터 가드 정책 통일):
- 라우터 전체: ``require_module(Module.DISTRIBUTION.value)`` — admin + 신사업팀 사용 가능.
- 위험 작업 (페르소나 등록/수정/삭제/credentials 변경/로그아웃/로그인 절차): endpoint 별 ``require_admin`` 추가.
- 조회/업로드/생성/헬스체크: 신사업팀 멤버 사용 가능.
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin, require_module
from app.models.user import User
from app.modules.constants import Module
from fastapi import UploadFile, File
from pathlib import Path
import tempfile
import shutil

from app.services.distribution.constants import DISTRIBUTION_COMPANIES

from app.schemas.distribution import (
    DataUploadResult,
    PersonaCreate,
    PersonaCredentialsUpdate,
    PersonaOut,
    PersonaUpdate,
    PersonaVerifyCode,
    ProductOut,
    WeeklySummaryOut,
)
from app.schemas.distribution_b2 import GenerateWeeklyRequest, GenerateWeeklyResult
from app.services.distribution import (
    data_service,
    generation_service,
    login_manager,
    persona_service,
)
from app.services.distribution.encryption import EncryptionError
from app.services.translation.translator import (
    RateLimitExceeded,
    check_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution"],
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, str]:
    """T9 모듈 헬스체크. 라우터 등록 검증용."""
    return {"status": "ok", "module": "distribution", "phase": "B-1"}


# ---------------------------------------------------------------------------
# Data Upload / Query (Phase B-1)
# ---------------------------------------------------------------------------


@router.post("/data/upload")
async def upload_data(
    file: UploadFile = File(...),
    company_label: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataUploadResult:
    """엑셀 파일 1개 업로드 → 종합관리시트 + 명품재고대장 동시 적재.

    Form 필드 (T9 Phase F-A):
    - file: .xlsx / .xlsm
    - company_label (optional): 4 회사 코드 중 하나 (TK101/래더엑스/뉴테인핏/SYBT).
      비어있으면 종합관리시트 R5 자동 추출, 그것도 없으면 "래더엑스" 폴백.

    DB 전략:
    - 종합관리시트: UNIQUE(company, period) UPSERT.
    - 명품재고대장: **회사별** wipe + insert — 다른 회사 데이터 보존.

    Errors:
    - 400: 파일 확장자 미지원 / 허용되지 않은 company_label.
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="엑셀 파일(.xlsx)만 업로드 가능합니다.",
        )

    # 회사 코드 검증 — 명시된 경우만. 빈 문자열도 None 처리.
    normalized_company = (company_label or "").strip() or None
    if normalized_company and normalized_company not in DISTRIBUTION_COMPANIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "허용된 회사 코드가 아닙니다. "
                f"가능: {list(DISTRIBUTION_COMPANIES)}"
            ),
        )

    # 임시 파일에 저장 (openpyxl 은 파일 경로가 필요).
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".xlsx"
    ) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = await data_service.ingest_excel(
            db,
            file_path=tmp_path,
            source_file_name=file.filename,
            user_id=current_user.id,
            company_label=normalized_company,
        )
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            logger.warning("임시 파일 삭제 실패: %s", tmp_path)

    return DataUploadResult(
        file_name=file.filename,
        company_label=result.company_label_used,
        summary_inserted=result.summary_inserted,
        summary_updated=result.summary_updated,
        products_inserted=result.products_inserted,
        products_wiped=result.products_wiped,
        warnings=result.warnings,
    )


@router.get("/data/weekly-summary")
async def list_weekly_summary(
    limit: int = 50,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    company_label: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[WeeklySummaryOut]]:
    """주차별 종합 데이터 조회. 기간 필터 + 회사 필터 옵션."""
    rows = await data_service.list_weekly_summary(
        db,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
        company_label=company_label,
    )
    return {"items": [WeeklySummaryOut.model_validate(r) for r in rows]}


@router.get("/data/products")
async def list_products(
    limit: int = 500,
    company_label: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[ProductOut]]:
    """명품재고대장 조회 (회사/브랜드/카테고리/검색 필터, 회사→브랜드→제품코드 정렬).

    필터 (T9 Phase F-A):
    - company_label: 정확 매칭. 미지정 시 전체 회사.
    - brand: 정확 매칭.
    - category: 정확 매칭 (Bag/Belts/Ring/Scarf 등).
    - search: 제품명(영문) / 제품코드 부분 매칭 (ILIKE).
    """
    rows = await data_service.list_products(
        db,
        limit=limit,
        company_label=company_label,
        brand=brand,
        category=category,
        search=search,
    )
    return {"items": [ProductOut.model_validate(r) for r in rows]}


@router.get("/data/companies")
async def list_companies() -> dict[str, list[str]]:
    """4 회사 코드 노출 — Agent D 가 Select 옵션에 사용 (T9 Phase F-A).

    회사 코드는 backend constants 의 ``DISTRIBUTION_COMPANIES`` 가 SSOT.
    프런트엔드 상수와 동기화 필요 시 이 엔드포인트 호출로 확인 가능.
    """
    return {"items": list(DISTRIBUTION_COMPANIES)}


# ---------------------------------------------------------------------------
# Generation Trigger (Phase B-2)
# ---------------------------------------------------------------------------

# D2: LLM 생성 비용 폭주 차단. 사용자별 분당/일일 호출 한도.
# translator.check_rate_limit(인메모리 슬라이딩 윈도우) 재사용 — 단일 인스턴스 전제.
# 일일 캡은 window_sec=86400 으로 같은 util 을 재사용하되, 분당 버킷과
# 충돌하지 않도록 키에 ":daily" 접미사를 붙인다.
_GEN_PER_MIN_MAX = 5
_GEN_DAILY_MAX = 50
_GEN_DAILY_WINDOW_SEC = 86_400


def _enforce_generation_limit(user_id: str) -> None:
    """생성 엔드포인트 공통 레이트리밋 (분당 + 일일 캡).

    Raises:
        HTTPException(429): 분당 또는 일일 한도 초과.
    """
    try:
        check_rate_limit(
            f"distgen:{user_id}",
            max_calls=_GEN_PER_MIN_MAX,
            window_sec=60,
        )
        check_rate_limit(
            f"distgen:daily:{user_id}",
            max_calls=_GEN_DAILY_MAX,
            window_sec=_GEN_DAILY_WINDOW_SEC,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="생성 요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        ) from exc


@router.post("/generate-weekly")
async def generate_weekly(
    payload: GenerateWeeklyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GenerateWeeklyResult:
    """4페어 (한국 N명 × 베트남 1명) × 시나리오 동시 생성.

    동작:
    - 최신 weekly_summary 1행 + 상위 명품제품 N개 컨텍스트로 구성
    - 활성 한국 페르소나(domestic_admin) 모두 + 첫 베트남 페르소나(vietnam_admin) 페어링
    - scenario_names 비어있으면 기본값 사용 (주간 정산 요약 + 명품 추가 매입 요청)
    - 결과 세션은 status='pending' — UI 검수 화면에서 승인 후 송신

    자격증명 없는 페르소나는 skip + warnings 누적.

    권한: DISTRIBUTION 모듈(admin + 신사업팀). LLM 생성 비용은 사용자별 분당/일일 호출 한도로 가드(D2).
    """
    _enforce_generation_limit(str(user.id))
    summary = await generation_service.generate_weekly_for_all_pairs(
        db,
        scenario_names=payload.scenario_names or None,
        company_label=payload.company_label,
    )
    return GenerateWeeklyResult(
        sessions_created=summary.sessions_created,
        skipped=summary.skipped,
        errors=summary.errors,
    )


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
    _: User = Depends(require_admin),
) -> PersonaOut:
    """새 페르소나 등록. **admin only** — credentials 입력 가드.

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
    _: User = Depends(require_admin),
) -> PersonaOut:
    """페르소나 부분 수정 (account_label, display_name, business_name, tone_profile, daily_msg_limit, active, warmup_until). **admin only**.

    account_label 변경 시 중복이면 409.
    """
    try:
        persona = await persona_service.update_persona(db, persona_id, payload)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 라벨(account_label)입니다.",
        ) from exc
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    return persona_service.to_out(persona)


@router.delete("/personas/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    """페르소나 hard delete + 세션 파일 삭제. **admin only**.

    관련 messages/sessions 는 RESTRICT FK 로 보호 (수동 정리).
    """
    ok = await persona_service.delete_persona(db, persona_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/personas/{persona_id}/credentials")
async def update_credentials(
    persona_id: UUID,
    payload: PersonaCredentialsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> PersonaOut:
    """자격증명 갱신 (placeholder seed 채우기 / 키 회전). **admin only** — 평문 api_hash 입력.

    기존 Telethon 세션이 있으면 무효화됨 → 재로그인 필요.
    """
    try:
        persona = await persona_service.update_credentials(
            db,
            persona_id,
            telegram_phone=payload.telegram_phone,
            api_id=payload.api_id,
            api_hash=payload.api_hash,
        )
    except EncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    return persona_service.to_out(persona)


@router.post("/personas/{persona_id}/logout")
async def logout_persona(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> PersonaOut:
    """세션 파일 삭제 + telegram_user_id/session_path 클리어. **admin only**. 자격증명은 보존."""
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
    _: User = Depends(require_admin),
) -> dict[str, str]:
    """SMS 인증 코드 발송 트리거. **admin only** — 텔레그램 계정 로그인 절차.

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
    _: User = Depends(require_admin),
) -> dict[str, object]:
    """SMS 코드 + (선택) 2FA 비밀번호 검증. **admin only** — 텔레그램 계정 로그인 절차.

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


@router.post("/personas/{persona_id}/sync")
async def sync_persona(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> PersonaOut:
    """연동된 텔레그램 계정 정보 재동기화. **admin only** (요구사항 2).

    재로그인(SMS) 없이 기존 세션으로 get_me() 호출 →
    display_name / telegram_username / last_login_at 갱신.
    account_label(코드명)·business_name(사업자명)은 보존.

    Errors:
    - 400: 자격증명 미설정.
    - 409: 로그인 세션 없음/만료 → 재로그인 필요.
    """
    persona = await persona_service.get_persona(db, persona_id)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음"
        )
    try:
        await login_manager.sync_persona_from_telegram(persona, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except login_manager.SyncNotLoggedInError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except EncryptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("persona sync 예외 — persona=%s", persona_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="정보 동기화 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
        ) from exc
    return persona_service.to_out(persona)
