"""텐센트 VOD AIGC ApiToken 자동 발급 + 캐시 매니저 (T8 후속).

배경:
    텐센트 MaaS는 두 단계의 API 체계로 동작.
    1) **VOD Token 발급**: ``vod.tencentcloudapi.com`` action ``CreateAigcApiToken``.
       TC3-HMAC-SHA256 시그니처 + body ``{"SubAppId": <int>}`` → ``{"ApiToken": "..."}``.
       발급된 ``ApiToken`` 의 실 TTL 은 1시간(추정).
    2) **VOD LLM Chat**: ``text-aigc.vod-qcloud.com/v1/chat/completions``, OpenAI-compatible,
       Bearer 헤더에 (1)에서 발급된 ``ApiToken`` 주입.

본 모듈은 (1) 단계를 자동화한다:
    - ``get_token()`` — 캐시 유효하면 그대로, 만료 임박이면 재발급.
    - 동시성 안전: ``asyncio.Lock`` 으로 동시 호출 시 한 번만 refresh.
    - Fallback: ``settings.tencent_aigc_api_key`` 가 수동 주입되어 있으면 그대로 반환
      (SecretId/Key 발급 전 단계 호환).

TC3-HMAC-SHA256 시그니처 알고리즘은 텐센트 v3 표준
(https://www.tencentcloud.com/document/product/213/30654) 을 따른다.

상태(시크릿/캐시)는 module-level 싱글톤으로만 유지. 별도 외부 캐시(redis 등) 불필요 —
프로세스 1개 가정, 만료 임박 시 재발급하면 됨.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 텐센트 v3 시그니처 상수 (CreateAigcApiToken은 VOD 서비스 산하).
# ---------------------------------------------------------------------------
_SERVICE = "vod"
_VERSION = "2018-07-17"  # VOD API 버전 (텐센트 공식 문서 기준).
_ACTION = "CreateAigcApiToken"
_ALGORITHM = "TC3-HMAC-SHA256"

# 새로 발급된 ApiToken 은 게이트웨이에서 활성화까지 ~10s 걸린다(라이브 확인:
# 발급 직후 401 → 10s 뒤 OK). 이 시간 지나야 사용 가능으로 간주한다.
_ACTIVATION_WAIT_S = 13.0
# 만료 이만큼 전부터 백그라운드 선발급(기존 토큰 서빙 중 새 토큰을 미리 활성화).
_REFRESH_AHEAD_S = 150.0


class TencentApiTokenManager:
    """VOD ApiToken 발급/캐시 매니저 (싱글톤).

    수동 키 fallback:
        ``settings.tencent_aigc_api_key`` 가 비어있지 않으면 무조건 그 값 반환 (refresh 안 함).
        SecretId/Key 발급 전 단계 또는 디버깅용.
    """

    def __init__(self) -> None:
        self._cached_token: str | None = None
        self._cached_until: datetime | None = None
        # 이 시각 이후에 활성(발급 후 활성 지연 흡수). 그 전엔 401 나므로 안 쓴다.
        self._cached_active_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._refreshing = False

    def _has_active(self, now: datetime) -> bool:
        return bool(
            self._cached_token
            and self._cached_until
            and self._cached_until > now
            and self._cached_active_at
            and now >= self._cached_active_at
        )

    async def get_token(self) -> str:
        """활성·유효한 토큰을 반환. 없으면 발급 후 활성까지 대기(콜드만 지연)."""
        # Fallback: 수동 키 우선.
        if settings.tencent_aigc_api_key:
            return settings.tencent_aigc_api_key

        now = datetime.now(timezone.utc)
        if self._has_active(now):
            # 만료 임박이면 백그라운드로 미리 재발급(기존 토큰은 계속 서빙).
            if (
                self._cached_until
                and (self._cached_until - now).total_seconds() < _REFRESH_AHEAD_S
                and not self._refreshing
            ):
                self._refreshing = True
                asyncio.create_task(self._refresh_in_background())
            return self._cached_token  # type: ignore[return-value]

        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._has_active(now):
                return self._cached_token  # type: ignore[return-value]

            token, expires_at = await self._refresh()
            active_at = datetime.now(timezone.utc) + timedelta(seconds=_ACTIVATION_WAIT_S)
            self._cached_token = token
            self._cached_until = expires_at
            self._cached_active_at = active_at
            logger.info(
                "텐센트 ApiToken 발급 — 활성 대기 %.0fs (만료: %s)",
                _ACTIVATION_WAIT_S,
                expires_at.isoformat(),
            )
            # 활성화 전 사용 시 401 → 활성까지 대기 후 반환(콜드 첫 호출만 지연).
            wait = (active_at - datetime.now(timezone.utc)).total_seconds()
            if wait > 0:
                await asyncio.sleep(wait)
            return token

    async def _refresh_in_background(self) -> None:
        """만료 전 미리 새 토큰 발급 → 활성 대기 → 교체. 대기 동안 기존 토큰 서빙."""
        try:
            token, expires_at = await self._refresh()
            await asyncio.sleep(_ACTIVATION_WAIT_S)  # 활성 대기(기존 토큰 계속 유효)
            self._cached_token = token
            self._cached_until = expires_at
            self._cached_active_at = datetime.now(timezone.utc)  # 이미 활성
            logger.info("텐센트 ApiToken 선발급·교체 완료 (만료: %s)", expires_at.isoformat())
        except Exception:  # noqa: BLE001 — 선발급 실패는 기존 토큰 만료 시 콜드 경로가 처리.
            logger.warning("텐센트 ApiToken 선발급 실패 — 만료 시 재시도", exc_info=True)
        finally:
            self._refreshing = False

    async def warmup(self) -> str:
        """시작 시 토큰을 미리 발급·활성화해 첫 대화의 401(활성 지연)을 없앤다."""
        return await self.get_token()

    async def _refresh(self) -> tuple[str, datetime]:
        """``CreateAigcApiToken`` 호출 → (ApiToken, 캐시 만료 시각) 반환."""
        if not settings.tencent_aigc_subapp_id:
            raise RuntimeError("텐센트 SubAppId 미설정 (TENCENT_AIGC_SUBAPP_ID)")
        if not settings.tencent_aigc_secret_id or not settings.tencent_aigc_secret_key:
            raise RuntimeError("텐센트 SecretId/Key 미설정")

        endpoint = settings.tencent_aigc_vod_endpoint
        region = settings.tencent_aigc_region
        host = endpoint
        url = f"https://{endpoint}"

        body_obj: dict[str, Any] = {"SubAppId": int(settings.tencent_aigc_subapp_id)}
        # canonical request 는 separators 고정된 JSON 사용 (서명 일관성).
        payload = json.dumps(body_obj, separators=(",", ":"))

        timestamp = int(datetime.now(timezone.utc).timestamp())
        headers = _build_signed_headers(
            secret_id=settings.tencent_aigc_secret_id,
            secret_key=settings.tencent_aigc_secret_key,
            service=_SERVICE,
            host=host,
            action=_ACTION,
            version=_VERSION,
            region=region,
            payload=payload,
            timestamp=timestamp,
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, content=payload)
            resp.raise_for_status()
            data = resp.json()

        # 텐센트 표준 응답 envelope: {"Response": {...}}.
        response = data.get("Response", {})
        if "Error" in response:
            err = response["Error"]
            raise RuntimeError(
                f"텐센트 CreateAigcApiToken 오류: {err.get('Code')} - {err.get('Message')}"
            )

        api_token = response.get("ApiToken")
        if not api_token:
            raise RuntimeError(
                f"텐센트 응답에 ApiToken 없음: {json.dumps(response)[:200]}"
            )

        # 보수적 TTL: 실 만료 1시간 가정, 55분 후 재발급 (config 값 사용).
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=settings.tencent_aigc_token_ttl_seconds
        )
        return api_token, expires_at


# ---------------------------------------------------------------------------
# TC3-HMAC-SHA256 시그니처 (텐센트 v3 표준).
# 단계: canonical request → string-to-sign → derive signing key → signature.
# ---------------------------------------------------------------------------
def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _build_signed_headers(
    *,
    secret_id: str,
    secret_key: str,
    service: str,
    host: str,
    action: str,
    version: str,
    region: str,
    payload: str,
    timestamp: int,
) -> dict[str, str]:
    """TC3-HMAC-SHA256 헤더 빌더. 텐센트 v3 공식 알고리즘 그대로."""
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    content_type = "application/json; charset=utf-8"

    # 1) Canonical request
    http_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = _sha256_hex(payload)
    canonical_request = (
        f"{http_method}\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{hashed_payload}"
    )

    # 2) String to sign
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = (
        f"{_ALGORITHM}\n"
        f"{timestamp}\n"
        f"{credential_scope}\n"
        f"{_sha256_hex(canonical_request)}"
    )

    # 3) Derive signing key
    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")

    # 4) Signature
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        f"{_ALGORITHM} "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": version,
        "X-TC-Region": region,
    }


# 모듈-레벨 싱글톤.
token_manager = TencentApiTokenManager()


__all__ = ["TencentApiTokenManager", "token_manager"]
