"""생성/채움 문서 결과물을 부서별 NAS 폴더에 사본 저장하는 공유 헬퍼.

경로 스킴: ``{docwork_nas_output_root}/{부서}/{YYYY-MM-DD}/{파일명}``
(소유자 승인 스킴, 기본 루트 ``/mnt/nas-rw/문서작업``).

best-effort: NAS 마운트가 없거나 쓰기 불가하면 경고만 남기고 None 반환 —
사용자의 다운로드/렌더를 절대 실패시키지 않는다.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# 부서 미지정 시 기본 폴더명.
_DEFAULT_DEPT = "공통"
# 파일명 길이 상한 (확장자 제외 본문 기준 대략치). 과도하게 긴 제목 방어.
_MAX_NAME_LEN = 150
# 동일 파일명 중복 시 카운터 상한 — 넘으면 저장 포기(이론상 도달 불가).
_MAX_DEDUP = 1000


def _sanitize_segment(value: str | None, *, fallback: str) -> str:
    """경로 1 세그먼트(부서명 등) 정화 — 구분자/트래버설 제거."""
    if not value:
        return fallback
    # 경로 구분자·상위참조 제거. 영문/한글/숫자/공백/일부 기호만 허용.
    cleaned = value.replace("/", "_").replace("\\", "_").strip().strip(".")
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
    return cleaned or fallback


def _sanitize_filename(filename: str) -> str:
    """파일명 정화 — 디렉토리 성분 제거, 트래버설/제어문자 차단, 길이 제한."""
    # 어떤 경로 성분도 신뢰하지 않고 basename만 취한다.
    base = os.path.basename(filename.replace("\\", "/")).strip()
    base = base.replace("/", "_")
    base = re.sub(r"[\x00-\x1f]", "", base)
    base = base.strip().strip(".")
    if not base:
        base = "문서"
    suffix = Path(base).suffix
    stem = base[: -len(suffix)] if suffix else base
    if len(stem) > _MAX_NAME_LEN:
        stem = stem[:_MAX_NAME_LEN]
    return f"{stem}{suffix}"


def _dedup_target(directory: Path, filename: str) -> Path:
    """동일 파일명 존재 시 ``(n)`` 카운터를 붙여 충돌 회피."""
    target = directory / filename
    if not target.exists():
        return target
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for counter in range(1, _MAX_DEDUP):
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
    return target  # 사실상 도달 불가 — 마지막엔 덮어쓰기 허용.


def save_to_nas(
    data: bytes,
    *,
    department: str | None,
    filename: str,
) -> str | None:
    """문서 bytes 를 ``{루트}/{부서}/{날짜}/{파일명}`` 에 사본 저장.

    Args:
        data: 저장할 문서 바이너리.
        department: 인증 사용자 부서. None/빈값이면 '공통'.
        filename: 사용자가 받는 파일명 (예: ``제목.docx``). 정화 후 사용.

    Returns:
        저장 경로 문자열. 마운트 부재/쓰기 실패 등 어떤 사유로든 저장 못 하면 None.
        절대 예외를 전파하지 않는다 (호출자 응답을 깨면 안 됨).
    """
    try:
        root = Path(settings.docwork_nas_output_root)
        dept_seg = _sanitize_segment(department, fallback=_DEFAULT_DEPT)
        date_seg = date.today().isoformat()
        safe_name = _sanitize_filename(filename)

        directory = root / dept_seg / date_seg
        directory.mkdir(parents=True, exist_ok=True)

        target = _dedup_target(directory, safe_name)
        target.write_bytes(data)

        # 트래버설 방어 — 최종 경로가 루트 밖이면 폐기.
        real_target = os.path.realpath(target)
        real_root = os.path.realpath(root)
        if not real_target.startswith(real_root + os.sep):
            logger.error("NAS 문서 저장 경로가 루트를 벗어남 — 폐기: %s", real_target)
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            return None

        logger.info("NAS 문서 사본 저장: %s", target)
        return str(target)
    except OSError as exc:
        logger.warning(
            "NAS 문서 사본 저장 실패(다운로드는 정상): dept=%s file=%s (%s)",
            department,
            filename,
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001 - best-effort, 절대 전파 금지
        logger.warning("NAS 문서 사본 저장 중 예외(무시): %s", exc)
        return None
