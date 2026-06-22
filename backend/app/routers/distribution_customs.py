"""면장(통관신고) 데이터 수집 라우터 (Priority 4).

엔드포인트 (prefix=/api/distribution/customs):
| 메서드 | 경로       | 설명                                          |
|--------|------------|-----------------------------------------------|
| POST   | /upload    | 면장 엑셀/PDF 업로드 → 파싱·UPSERT + 미리보기 |
| GET    | /          | 면장 목록 (회사/검색 필터, 페이지네이션)    |
| GET    | /summary   | 집계 (건수 + 신고가 합 vs 실가 역산 합)     |

핵심 비즈니스 규칙:
- 면장 신고가는 관세 절감 목적으로 실가의 75% 로 신고된다.
- 실가 역산: actual_price = declared_price / 0.75 (비율 config 조정 가능).

권한 (T9 정책 통일):
- 라우터 전체: ``require_module(Module.DISTRIBUTION.value)`` — admin + 신사업팀.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.user import User
from app.modules.constants import Module
from app.schemas.distribution_customs import (
    CustomsDeclarationOut,
    CustomsListResponse,
    CustomsPreviewRow,
    CustomsSummaryOut,
    CustomsUploadResult,
)
from app.services.distribution import customs_service
from app.services.distribution.constants import DISTRIBUTION_COMPANIES

logger = logging.getLogger(__name__)

# 업로드 크기 상한 (메모리 고갈/zip-bomb 방지). 면장 엑셀/PDF 는 통상 수 MB.
# PDF 의 페이지 수 폭증(huge-page DoS)은 파서(_PDF_MAX_PAGES)에서 추가 방어.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

# 허용 확장자. 엑셀(.xlsx/.xlsm) + 면장 PDF(.pdf).
_ALLOWED_EXTENSIONS = (".xlsx", ".xlsm", ".pdf")

router = APIRouter(
    prefix="/api/distribution/customs",
    tags=["distribution-customs"],
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
)


@router.post("/upload")
async def upload_customs(
    file: UploadFile = File(...),
    company_label: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CustomsUploadResult:
    """면장 엑셀(.xlsx/.xlsm)/PDF(.pdf) 업로드 → 파싱 + 신고번호 기준 UPSERT.

    Form 필드:
    - file: .xlsx / .xlsm / .pdf
    - company_label (optional): 4 회사 코드 중 하나. 비어있으면 NULL 적재.

    멱등: 동일 신고번호 재업로드 시 기존 행 갱신 (중복 INSERT 없음).

    Errors:
    - 400: 파일 확장자 미지원 / 허용되지 않은 company_label / 빈 파일.
    """
    if not file.filename or not file.filename.lower().endswith(_ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="엑셀(.xlsx/.xlsm) 또는 PDF(.pdf) 파일만 업로드 가능합니다.",
        )

    normalized_company = (company_label or "").strip() or None
    if normalized_company and normalized_company not in DISTRIBUTION_COMPANIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "허용된 회사 코드가 아닙니다. "
                f"가능: {list(DISTRIBUTION_COMPANIES)}"
            ),
        )

    file_bytes = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="파일이 너무 큽니다. (최대 10MB)",
        )
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 파일입니다.",
        )

    try:
        result = await customs_service.ingest_customs(
            db,
            file_bytes=file_bytes,
            source_file_name=file.filename,
            user_id=current_user.id,
            company_label=normalized_company,
        )
    except Exception as exc:
        logger.exception("면장 업로드 처리 실패 — file=%s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="면장 파일 처리 중 오류가 발생했습니다. 파일 형식을 확인하세요.",
        ) from exc

    return CustomsUploadResult(
        file_name=file.filename,
        company_label=normalized_company,
        parsed=result.parsed,
        inserted=result.inserted,
        updated=result.updated,
        preview=[
            CustomsPreviewRow(
                declaration_type=row.declaration_type,
                declaration_number=row.declaration_number,
                item_name=row.item_name,
                product=row.product,
                bl_number=row.bl_number,
                unit_price=row.unit_price,
                declared_price=row.declared_price,
                declared_price_krw=row.declared_price_krw,
                actual_price=row.actual_price,
                currency=row.currency,
                stock_qty=row.stock_qty,
                declared_at=row.declared_at,
            )
            for row in result.preview
        ],
        warnings=result.warnings,
    )


@router.get("/")
async def list_customs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    company_label: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> CustomsListResponse:
    """면장 목록 조회. 회사/검색 필터 + 페이지네이션.

    - company_label: 정확 매칭. 미지정 시 전체 회사.
    - search: 신고번호 / 품명 / BL번호 부분 매칭 (ILIKE).
    """
    rows, total = await customs_service.list_declarations(
        db,
        limit=limit,
        offset=offset,
        company_label=company_label,
        search=search,
    )
    return CustomsListResponse(
        items=[CustomsDeclarationOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{declaration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customs(
    declaration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """면장 1행 삭제. 잘못 업로드한 행을 사용자가 직접 제거할 수 있게 한다.

    H2: declaration_id 는 ``uuid.UUID`` 타입 — 형식 오류는 FastAPI 가 422 로 거른다
    (DB 캐스트 500 방지).

    Errors:
    - 404: 해당 id 없음 (이미 삭제됐거나 존재하지 않음).
    - 422: declaration_id 가 UUID 형식이 아님.
    """
    deleted = await customs_service.delete_declaration(db, str(declaration_id))
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 면장 행을 찾을 수 없습니다 (이미 삭제됐을 수 있음).",
        )


@router.get("/summary")
async def customs_summary(
    company_label: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> CustomsSummaryOut:
    """면장 집계 — 건수 + 총 신고가 vs 총 실가(역산).

    역산 효과를 한눈에: 총 실가 ≈ 총 신고가 / 0.75.
    """
    result = await customs_service.summary(db, company_label=company_label)
    return CustomsSummaryOut(
        count=result.count,
        total_declared=result.total_declared,
        total_actual=result.total_actual,
        declare_ratio=settings.distribution_customs_declare_ratio,
    )
