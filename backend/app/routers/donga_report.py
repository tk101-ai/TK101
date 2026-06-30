"""동아제약 운영보고서 자동작성 라우터 (테스트 워크스페이스).

엔드포인트:
| 메서드 | 경로                              | 설명                                    |
|--------|-----------------------------------|-----------------------------------------|
| GET    | /api/donga-report/status          | 설정 점검(키/양식 준비 여부)            |
| POST   | /api/donga-report/generate        | 월 지정 → 운영보고서 .pptx 다운로드     |

권한: `require_module("test_workspace")` — admin + grant 받은 부서.
"""
from __future__ import annotations

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.config import settings
from app.dependencies import get_current_user, require_module
from app.models.user import User
from app.modules.constants import Module
from app.services.donga_report.service import generate_report

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/donga-report",
    tags=["donga-report"],
    dependencies=[Depends(require_module(Module.TEST_WORKSPACE.value))],
)

_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.get("/status")
async def status(_: User = Depends(get_current_user)) -> dict:
    """설정 준비 상태(라이브 시트 키·양식 파일)."""
    from pathlib import Path

    return {
        "sheet_id": settings.donga_sheet_id,
        "api_key_set": bool(settings.google_sheets_api_key),
        "template_exists": Path(settings.donga_report_template_path).is_file(),
        "template_path": settings.donga_report_template_path,
    }


@router.post("/generate")
async def generate(
    month: int,
    year: int = 2026,
    basis_date: str | None = None,
    include_narrative: bool = True,
    user: User = Depends(get_current_user),
) -> Response:
    """지정 월의 운영보고서 .pptx 생성 후 다운로드. 라이브 구글시트에서 자료를 읽는다."""
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="month 는 1~12 사이여야 합니다")
    try:
        pptx, meta = await generate_report(
            month=month, year=year, basis_date=basis_date,
            include_narrative=include_narrative,
        )
    except RuntimeError as exc:
        logger.warning("동아 운영보고서 생성 실패: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fname = f"동아제약_운영보고서_{year}년{month}월_초안.pptx"
    cd = "attachment; filename*=UTF-8''" + urllib.parse.quote(fname)
    logger.info("동아 운영보고서 다운로드 user=%s meta=%s", user.id, meta)
    return Response(
        content=pptx,
        media_type=_PPTX_MIME,
        headers={
            "Content-Disposition": cd,
            "X-Report-Meta": f"china={meta['china_count']},na={meta['na_count']}",
        },
    )
