"""백엔드 로그 NAS 영구 저장 (T8 Playground 백엔드 확장 — 2026-05-19).

``settings.playground_log_path`` 에 RotatingFileHandler 부착:
- backend.log : INFO 이상, 10MB × 5 회전.
- error.log   : ERROR 이상 (별도 파일).

NAS 마운트 디렉토리가 없으면 자동 생성 (mkdir -p). 만약 권한이 없거나
경로가 잘못되어 핸들러 생성이 실패하면 stdout 만 사용하고 경고 로그.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from app.config import settings

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5


def setup_logging() -> None:
    """startup 시 1회 호출. 중복 부착 방지를 위해 핸들러 이름으로 체크."""
    root = logging.getLogger()
    # 기존 항목과 동일 핸들러 중복 방지.
    existing_names = {getattr(h, "_tk101_name", None) for h in root.handlers}

    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT)

    try:
        log_path = settings.playground_log_path
        log_dir = os.path.dirname(log_path) or "."
        os.makedirs(log_dir, exist_ok=True)

        if "tk101_backend_log" not in existing_names:
            backend_handler = RotatingFileHandler(
                log_path,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            backend_handler.setLevel(logging.INFO)
            backend_handler.setFormatter(formatter)
            backend_handler._tk101_name = "tk101_backend_log"  # type: ignore[attr-defined]
            root.addHandler(backend_handler)

        if "tk101_error_log" not in existing_names:
            error_path = os.path.join(log_dir, "error.log")
            error_handler = RotatingFileHandler(
                error_path,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            error_handler._tk101_name = "tk101_error_log"  # type: ignore[attr-defined]
            root.addHandler(error_handler)
    except OSError as exc:
        # 디렉토리 생성 실패 / 권한 없음 / 디스크 풀 — stdout 만 사용.
        logging.getLogger(__name__).warning(
            "백엔드 로그 파일 핸들러 부착 실패 (path=%s): %s. stdout 만 사용합니다.",
            settings.playground_log_path,
            exc,
        )


__all__ = ["setup_logging"]
