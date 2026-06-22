"""forms 라우터의 비-HTTP 보조 로직: 파일 저장/경로 검증, 상태 전이 가드,
템플릿 버전 계산, 템플릿 markdown 로드, UUID 변환.

forms 라우터 분할(동작 동일 리팩터)에서 라우터 본문 밖으로 추출한 헬퍼들이다.
로직/시그니처/예외는 원본과 동일하다.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.form_filler import analyzer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상태 전이 가드 (NFR-04 #4 검수 강제)
# ---------------------------------------------------------------------------

# 허용 상태 전이 그래프. completed 는 반드시 reviewing 단계를 거쳐야 함.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "analyzing": {"collecting", "failed"},
    "collecting": {"mapping", "failed"},
    "mapping": {"reviewing", "failed"},
    "reviewing": {"reviewing", "completed", "failed"},  # 검수 단계 내 PATCH 허용
    "completed": set(),  # terminal
    "failed": set(),
}


def enforce_status_transition(current: str, new: str) -> None:
    """검수 강제 (NFR-04 #4): reviewing 거치지 않은 completed 차단."""
    if current == new:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"잡 상태 전이 거부: {current} → {new}. "
                f"검수 강제 정책 — completed 는 반드시 reviewing 을 거쳐야 합니다."
            ),
        )


# ---------------------------------------------------------------------------
# 파일 저장 / 경로 검증
# ---------------------------------------------------------------------------


def save_template_file(file_bytes: bytes, file_hash: str, original_name: str) -> str:
    """양식 원본을 NAS 출력 루트의 templates 하위에 file_hash 키로 저장."""
    root = Path(settings.form_filler_output_root) / "templates"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{file_hash}{Path(original_name).suffix.lower()}"
    target.write_bytes(file_bytes)
    return str(target)


def save_upload_file(file_bytes: bytes, original_name: str, job_id: str) -> str:
    root = Path(settings.form_filler_upload_root) / job_id
    root.mkdir(parents=True, exist_ok=True)
    safe_name = original_name.replace("/", "_").replace("\\", "_")
    target = root / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    target.write_bytes(file_bytes)
    real_target = os.path.realpath(target)
    real_root = os.path.realpath(settings.form_filler_upload_root)
    # separator 없는 startswith 우회(/root-evil ⊂ /root) 차단 — 경계 검사.
    if not (real_target == real_root or real_target.startswith(real_root + os.sep)):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="업로드 경로가 허용 범위를 벗어남",
        )
    return str(target)


# ---------------------------------------------------------------------------
# 변환 / 로드 헬퍼
# ---------------------------------------------------------------------------


def safe_uuid(value: str | None) -> uuid.UUID | None:
    """문자열 → UUID. Qdrant point id 는 UUID(uuid5)지만 방어적으로 변환 실패는 None."""
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def try_load_template_markdown(template: Any) -> str:
    """template.file_path 의 .docx 를 markdown 으로 변환. 실패 시 빈 문자열."""
    try:
        with open(template.file_path, "rb") as f:
            return analyzer.docx_to_markdown(f.read())
    except (OSError, RuntimeError) as exc:
        logger.warning("템플릿 markdown 로드 실패: %s — 빈 문자열 사용", exc)
        return ""


async def next_template_version(
    db: AsyncSession, name: str, form_template_model: Any
) -> int:
    stmt = select(form_template_model).where(form_template_model.name == name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return (max((int(r.version or 1) for r in rows), default=0) + 1) if rows else 1
