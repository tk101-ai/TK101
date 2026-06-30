"""구글시트(관리문서) 라이브 읽기 — Sheets API v4 + API 키.

시트가 '링크 공유' 상태라 서비스 계정 없이 **API 키만으로** 공개 읽기가 된다.
탭(워크시트) 단위로 values 를 받아 sheet_parser 가 쓰는 행(list[list]) 형태로
반환한다. 키 미설정/네트워크 실패는 명확한 RuntimeError 로 올려 라우터가 사용자
메시지로 변환한다(업로드 폴백은 라우터 책임).

값 렌더: FORMATTED_VALUE — 화면에 보이는 문자열(날짜 'YYYY-MM-DD …', 숫자 콤마
포함)로 받아 sheet_parser 의 정규화(_to_int/_to_date)와 일관되게 처리한다.
"""
from __future__ import annotations

import urllib.parse

import httpx

from app.config import settings

_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
_TIMEOUT_S = 20.0


async def fetch_tab(sheet_id: str, tab_name: str, *, api_key: str | None = None) -> list[list]:
    """한 탭의 값 전체를 list[list] 로 반환. 빈 셀은 행 길이에 따라 누락될 수 있어
    sheet_parser 의 안전 인덱싱(_cell)과 함께 쓴다."""
    key = api_key or settings.google_sheets_api_key
    if not key:
        raise RuntimeError("GOOGLE_SHEETS_API_KEY 가 설정되지 않았습니다")
    # 탭 이름을 range 로(전체 탭). 한글·특수문자 인코딩 + 작은따옴표로 감싼다.
    rng = urllib.parse.quote(f"'{tab_name}'")
    url = f"{_API_BASE}/{sheet_id}/values/{rng}"
    params = {
        "key": key,
        "valueRenderOption": "FORMATTED_VALUE",
        "dateTimeRenderOption": "FORMATTED_STRING",
        "majorDimension": "ROWS",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"구글시트 요청 실패: {exc}") from exc
    if resp.status_code == 403:
        raise RuntimeError(
            "구글시트 접근 거부(403) — API 키 권한 또는 시트 공유 설정을 확인하세요"
        )
    if resp.status_code == 400:
        raise RuntimeError(f"구글시트 탭 '{tab_name}' 을 찾을 수 없습니다(범위 오류)")
    if resp.status_code != 200:
        raise RuntimeError(f"구글시트 응답 오류 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data.get("values", []) or []
