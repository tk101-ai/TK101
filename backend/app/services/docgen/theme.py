"""문서 생성 테마 — 색·폰트·로고·템플릿을 한 곳에 모은 디자인 토큰.

pptx_builder / docx_builder 가 공유한다. 기본값은 단정한 비즈니스 테마(딥 네이비 +
포인트 블루)이며, settings(docgen_brand_*, docgen_*_template, docgen_logo_path)로
회사 색/템플릿/로고를 주입하면 그대로 반영된다("알아서 기본 테마" + "기존 템플릿" 둘 다).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.config import settings

# 한글 글리프가 안전하게 렌더되는 폰트(윈도우 PowerPoint/Word 기본 탑재).
_HEADING_FONT = "맑은 고딕"
_BODY_FONT = "맑은 고딕"


def _hex_to_rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    """'#RRGGBB' 또는 'RRGGBB' → (r, g, b). 형식 오류면 fallback."""
    s = (value or "").strip().lstrip("#")
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return fallback


def _mix(color: tuple[int, int, int], white_ratio: float) -> tuple[int, int, int]:
    """color 를 흰색과 섞어 옅은 톤 생성(표 줄무늬·배경용). white_ratio 0~1."""
    r, g, b = color
    w = max(0.0, min(1.0, white_ratio))
    return (
        round(r + (255 - r) * w),
        round(g + (255 - g) * w),
        round(b + (255 - b) * w),
    )


def _shade(color: tuple[int, int, int], black_ratio: float) -> tuple[int, int, int]:
    """color 를 검정과 섞어 더 짙은 톤 생성(표지 레이어 깊이용). black_ratio 0~1."""
    r, g, b = color
    k = max(0.0, min(1.0, black_ratio))
    return (round(r * (1 - k)), round(g * (1 - k)), round(b * (1 - k)))


def _series_palette(
    primary: tuple[int, int, int], accent: tuple[int, int, int]
) -> tuple[tuple[int, int, int], ...]:
    """브랜드 색에서 파생한 차트 시리즈 팔레트(최대 6색).

    Office 기본 차트색(빨강·주황 등 브랜드와 무관) 대신, accent/primary 와 그
    명/암 변주로 한 덱 안에서 톤이 일관된 데이터 시각화를 만든다. 시리즈가 6개를
    넘으면 순환한다(렌더러에서 mod).
    """
    return (
        accent,
        primary,
        _mix(accent, 0.42),
        _shade(primary, 0.28),
        _mix(primary, 0.5),
        _shade(accent, 0.32),
    )


@dataclass(frozen=True)
class Theme:
    """문서 디자인 토큰. RGB는 (r, g, b) 튜플."""

    primary: tuple[int, int, int]        # 표지 배경·제목바·표 헤더
    accent: tuple[int, int, int]         # 강조선·차트·하이라이트
    text: tuple[int, int, int]           # 본문 텍스트
    muted: tuple[int, int, int]          # 보조 텍스트(부제·푸터)
    light_bg: tuple[int, int, int]       # 옅은 배경(목차 카드 등)
    table_stripe: tuple[int, int, int]   # 표 짝수행 음영
    white: tuple[int, int, int]
    primary_deep: tuple[int, int, int]   # 표지 레이어 깊이(짙은 primary)
    accent_soft: tuple[int, int, int]    # 강조 칩/로젠지 옅은 채움
    surface: tuple[int, int, int]        # 카드·구분 슬라이드 중성 배경(거의 흰색)
    hairline: tuple[int, int, int]       # 옅은 구분선
    series_palette: tuple[tuple[int, int, int], ...]  # 차트 시리즈 색(브랜드 파생)
    heading_font: str
    body_font: str
    footer_text: str
    logo_path: str | None
    pptx_template: str | None
    docx_template: str | None

    @property
    def primary_hex(self) -> str:
        return "{:02X}{:02X}{:02X}".format(*self.primary)

    @property
    def accent_hex(self) -> str:
        return "{:02X}{:02X}{:02X}".format(*self.accent)


def _existing(path: str | None) -> str | None:
    """경로가 실제 존재하면 반환, 아니면 None(설정만 있고 파일 없을 때 안전)."""
    if path and os.path.isfile(path):
        return path
    return None


def get_theme() -> Theme:
    """settings 기반 현재 테마 구성. 색/템플릿/로고를 env로 덮어쓸 수 있다."""
    primary = _hex_to_rgb(settings.docgen_brand_primary, (0x16, 0x33, 0x5B))
    accent = _hex_to_rgb(settings.docgen_brand_accent, (0x2D, 0x7F, 0xF9))
    text = _hex_to_rgb(settings.docgen_brand_text, (0x1A, 0x22, 0x30))
    return Theme(
        primary=primary,
        accent=accent,
        text=text,
        muted=_mix(text, 0.45),
        light_bg=_mix(primary, 0.93),
        table_stripe=_mix(accent, 0.90),
        white=(0xFF, 0xFF, 0xFF),
        primary_deep=_shade(primary, 0.32),
        accent_soft=_mix(accent, 0.84),
        surface=_mix(primary, 0.965),
        hairline=_mix(text, 0.82),
        series_palette=_series_palette(primary, accent),
        heading_font=_HEADING_FONT,
        body_font=_BODY_FONT,
        footer_text=settings.docgen_footer_text or "",
        logo_path=_existing(settings.docgen_logo_path),
        pptx_template=_existing(settings.docgen_pptx_template),
        docx_template=_existing(settings.docgen_docx_template),
    )
