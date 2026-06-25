"""render_markdown 미리보기 — chart/layout 펜스가 읽기 좋은 마크다운으로 치환되는지.

LLM 호출 없음(순수 변환 로직). 레이아웃 펜스의 날 JSON 이 미리보기에 노출되지 않고
내용은 보존되는지 검증한다.
"""
from __future__ import annotations

from app.services.docgen.generator import render_markdown


def _md(body: str) -> str:
    return render_markdown("제목", [{"heading": "섹션", "body": body}])


def test_kpi_layout_rendered_as_list_not_raw_json() -> None:
    body = ('```layout\n{"layout":"kpi","title":"핵심 지표",'
            '"items":[{"value":"+42%","label":"매출","caption":"전년比"}]}\n```')
    out = _md(body)
    assert '"layout"' not in out  # 날 JSON 미노출.
    assert "핵심 지표" in out
    assert "**+42%**" in out and "매출" in out


def test_steps_layout_numbered() -> None:
    body = ('```layout\n{"layout":"steps","steps":[{"title":"분석","detail":"진단"},'
            '{"title":"설계"}]}\n```')
    out = _md(body)
    assert "1. 분석" in out and "2. 설계" in out


def test_quote_layout_blockquote() -> None:
    body = '```layout\n{"layout":"quote","text":"속도가 경쟁력","attribution":"TF"}\n```'
    out = _md(body)
    assert "> 속도가 경쟁력" in out and "TF" in out


def test_compare_layout_columns() -> None:
    body = ('```layout\n{"layout":"compare","columns":[{"heading":"기존","points":["느림"]},'
            '{"heading":"제안","points":["빠름"]}]}\n```')
    out = _md(body)
    assert "**기존**" in out and "느림" in out and "**제안**" in out


def test_invalid_layout_json_safe_fallback() -> None:
    out = _md("```layout\n{not json}\n```")
    assert "🧩" in out  # 폴백 표기, 크래시 없음.


def test_chart_fence_still_converted() -> None:
    body = ('```chart\n{"type":"bar","title":"매출","categories":["A"],'
            '"series":[{"name":"s","values":[1]}]}\n```')
    out = _md(body)
    assert "📊" in out and "매출" in out


def test_plain_body_unchanged() -> None:
    out = _md("그냥 문단과\n- 불릿")
    assert "그냥 문단과" in out and "- 불릿" in out
