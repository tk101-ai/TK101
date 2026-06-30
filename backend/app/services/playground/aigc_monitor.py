"""텐센트 AIGC 게이트웨이 사용량·Quota 모니터링 (관리자 대시보드).

가이드(doc.tencentpoc.com) 기반. VOD 액션 `DescribeAigcUsageData`(기간별 사용량)·
`DescribeAigcQuotas`(한도)를 TC3-HMAC 서명으로 호출한다. 서명은 token_manager 의
공용 빌더를 재사용한다. 인증/네트워크 실패는 빈 결과로 graceful 처리(대시보드가
깨지지 않게).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.services.playground.token_manager import _build_signed_headers

logger = logging.getLogger(__name__)

AIGC_TYPES = ("Text", "Image", "Video")
_VERSION = "2018-07-17"
_SERVICE = "vod"


async def _vod_call(action: str, body: dict) -> dict:
    """서명된 VOD 액션 호출 → Response dict(실패 시 {'Error':...})."""
    if not (settings.tencent_aigc_secret_id and settings.tencent_aigc_secret_key
            and settings.tencent_aigc_subapp_id):
        return {"Error": {"Code": "NotConfigured", "Message": "텐센트 자격증명 미설정"}}
    endpoint = settings.tencent_aigc_vod_endpoint
    payload = json.dumps(body, separators=(",", ":"))
    ts = int(datetime.now(timezone.utc).timestamp())
    headers = _build_signed_headers(
        secret_id=settings.tencent_aigc_secret_id,
        secret_key=settings.tencent_aigc_secret_key,
        service=_SERVICE, host=endpoint, action=action, version=_VERSION,
        region=settings.tencent_aigc_region, payload=payload, timestamp=ts,
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"https://{endpoint}", headers=headers, content=payload)
            return resp.json().get("Response", {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("AIGC 모니터 호출 실패(%s): %s", action, exc)
        return {"Error": {"Code": "RequestFailed", "Message": str(exc)}}


def _norm_usage(resp: dict) -> list[dict]:
    """DescribeAigcUsageData 응답 → [{date, count, usage}] 평탄화."""
    out: list[dict] = []
    for series in resp.get("AigcUsageDataSet", []) or []:
        for d in series.get("DataSet", []) or []:
            out.append({
                "date": (d.get("Time") or "")[:10],
                "count": d.get("Count", 0) or 0,
                "usage": d.get("Usage", 0) or 0,
            })
    return out


async def get_overview(days: int = 14) -> dict:
    """타입별(Text/Image/Video) 사용량 시계열 + 현재 Quota. 관리자 대시보드용."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, days))
    s, e = start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")
    sub = int(settings.tencent_aigc_subapp_id) if settings.tencent_aigc_subapp_id else 0

    async def one(t: str) -> tuple[str, dict]:
        usage_resp, quota_resp = await asyncio.gather(
            _vod_call("DescribeAigcUsageData", {"SubAppId": sub, "AigcType": t, "StartTime": s, "EndTime": e}),
            _vod_call("DescribeAigcQuotas", {"SubAppId": sub, "QuotaType": t}),
        )
        usage = _norm_usage(usage_resp)
        return t, {
            "usage": usage,
            "total_count": sum(x["count"] for x in usage),
            "total_usage": sum(x["usage"] for x in usage),
            "quotas": quota_resp.get("QuotaSet", []) or [],
            "error": usage_resp.get("Error", {}).get("Message") if "Error" in usage_resp else None,
        }

    results = await asyncio.gather(*[one(t) for t in AIGC_TYPES])
    return {
        "subapp_id": settings.tencent_aigc_subapp_id,
        "days": days,
        "start": s,
        "end": e,
        "types": {t: data for t, data in results},
    }
