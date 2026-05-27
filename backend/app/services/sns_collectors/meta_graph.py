"""Meta Graph API 공통 클라이언트.

Facebook / Instagram 수집기가 공유하는 저수준 HTTP 래퍼.
- 토큰/앱 시크릿은 config(settings)에서만 읽는다 (하드코딩 금지).
- appsecret_proof(앱 시크릿 HMAC)를 자동 첨부해 토큰 탈취 위험을 낮춘다.
- 페이지네이션(paging.next) 자동 추적.
- Graph 오류는 CollectorError(한국어 메시지)로 변환해 라우터/UI 가 표시할 수 있게 한다.

토큰이 비어 있으면 require_token() 이 즉시 CollectorError 를 던진다 (HTTP 501 아님).
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.sns_collectors.base import CollectorError

GRAPH_BASE = "https://graph.facebook.com"
# paging.next 는 이 호스트만 허용 (SSRF 방지 — Graph 가 돌려준 절대 URL 검증).
_GRAPH_HOST = "graph.facebook.com"
HTTP_TIMEOUT_SECONDS = 20.0
# paging.next 추적 시 무한루프 방지용 상한.
MAX_PAGES = 50
# 오류 메시지에 토큰이 섞여 나올 때 마스킹 (API 응답/로그 노출 방지).
_TOKEN_RE = re.compile(r"(EAA[A-Za-z0-9]{8,}|access_token=[^&\s]+)")


def _redact(text: str) -> str:
    """토큰류 문자열을 [REDACTED] 로 치환."""
    return _TOKEN_RE.sub("[REDACTED]", text)


def require_token() -> str:
    """설정된 Meta 액세스 토큰을 반환. 없으면 한국어 에러."""
    token = settings.meta_access_token
    if not token:
        raise CollectorError(
            "메타 API 토큰 미설정 — .env 에 META_ACCESS_TOKEN 을 등록해야 "
            "자동 수집/메트릭이 동작합니다. (수동 콘텐츠 등록은 토큰 없이도 가능)"
        )
    return token


def _appsecret_proof(token: str) -> str | None:
    """app secret 이 설정돼 있으면 appsecret_proof(HMAC-SHA256) 생성."""
    secret = settings.meta_app_secret
    if not secret:
        return None
    return hmac.new(
        secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def base_params(token: str | None = None) -> dict[str, str]:
    """Graph 호출 공통 파라미터(access_token + appsecret_proof)."""
    resolved = token or require_token()
    params: dict[str, str] = {"access_token": resolved}
    proof = _appsecret_proof(resolved)
    if proof:
        params["appsecret_proof"] = proof
    return params


def _graph_url(path: str) -> str:
    version = settings.meta_graph_version or "v21.0"
    normalized = path.lstrip("/")
    return f"{GRAPH_BASE}/{version}/{normalized}"


def _raise_for_graph_error(response: httpx.Response) -> dict[str, Any]:
    """Graph 응답 파싱 + 오류를 CollectorError 로 변환."""
    try:
        data = response.json()
    except ValueError as exc:
        raise CollectorError(f"메타 API 응답 파싱 실패: {exc}") from exc
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = _redact(err.get("message", "알 수 없는 오류"))
        code = err.get("code", "?")
        raise CollectorError(f"메타 API 오류(code={code}): {msg}")
    if response.status_code >= 400:
        raise CollectorError(
            f"메타 API HTTP {response.status_code}: {_redact(response.text[:200])}"
        )
    return data


async def graph_get(
    path: str,
    params: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Graph GET 단일 호출. 오류는 CollectorError 로 변환."""
    query = base_params(token)
    if params:
        query.update({k: v for k, v in params.items() if v is not None})
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(_graph_url(path), params=query)
        except httpx.HTTPError as exc:
            raise CollectorError(f"메타 API 호출 실패: {exc}") from exc
    return _raise_for_graph_error(response)


async def graph_get_paged(
    path: str,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    """paging.next 를 따라가며 data 배열을 모두 모은다."""
    resolved = token or require_token()
    query = base_params(resolved)
    if params:
        query.update({k: v for k, v in params.items() if v is not None})

    items: list[dict[str, Any]] = []
    url: str | None = _graph_url(path)
    next_params: dict[str, Any] | None = query
    pages = 0
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        while url and pages < max_pages:
            try:
                response = await client.get(url, params=next_params)
            except httpx.HTTPError as exc:
                raise CollectorError(f"메타 API 호출 실패: {exc}") from exc
            data = _raise_for_graph_error(response)
            items.extend(data.get("data") or [])
            paging = data.get("paging") or {}
            url = paging.get("next")  # next 는 토큰 포함 절대 URL
            if url and urlparse(url).netloc != _GRAPH_HOST:
                raise CollectorError(
                    f"예상치 못한 paging.next 호스트: {urlparse(url).netloc}"
                )
            next_params = None
            pages += 1
    return items


def safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
