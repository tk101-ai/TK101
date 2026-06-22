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
        heading_font=_HEADING_FONT,
        body_font=_BODY_FONT,
        footer_text=settings.docgen_footer_text or "",
        logo_path=_existing(settings.docgen_logo_path),
        pptx_template=_existing(settings.docgen_pptx_template),
        docx_template=_existing(settings.docgen_docx_template),
    )
