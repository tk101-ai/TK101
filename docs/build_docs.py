"""
TK101 AI - 아키텍처 문서 빌드 스크립트
- 통합 PDF (ARCHITECTURE + SITEMAP + DEVELOPMENT_GUIDE)
- ARCHITECTURE 단독 PDF
- 마스터 구성도 PNG (한 장)

사용법:
    python docs/build_docs.py
"""
import io
import pathlib
import re
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import markdown

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "_build"
OUT.mkdir(exist_ok=True)

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# -----------------------------------------------------------------------------
# 공통 CSS — 보고서 스타일
# -----------------------------------------------------------------------------
REPORT_CSS = r"""
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Malgun Gothic", "맑은 고딕", -apple-system, "Segoe UI", sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: #1f2937;
  max-width: 100%;
  margin: 0 auto;
  padding: 0;
}
.cover {
  text-align: center;
  padding: 80px 0 60px;
  page-break-after: always;
}
.cover .badge {
  display: inline-block;
  padding: 4px 14px;
  background: #1e40af;
  color: white;
  border-radius: 20px;
  font-size: 11pt;
  margin-bottom: 30px;
  letter-spacing: 1px;
}
.cover h1 {
  font-size: 32pt;
  color: #1e3a8a;
  border: none;
  margin: 10px 0;
}
.cover .subtitle {
  font-size: 14pt;
  color: #475569;
  margin-top: 8px;
}
.cover .meta {
  margin-top: 60px;
  font-size: 11pt;
  color: #64748b;
  line-height: 1.9;
}
.cover .meta strong { color: #1e3a8a; font-weight: 600; }
.toc {
  page-break-after: always;
  padding: 20px 0;
}
.toc h2 {
  font-size: 18pt;
  color: #1e3a8a;
  border-bottom: 2px solid #1e40af;
  padding-bottom: 6px;
}
.toc ol { font-size: 11pt; line-height: 2; padding-left: 24px; }
.toc ol li::marker { color: #1e40af; font-weight: 600; }
.section { page-break-before: always; }
h1 {
  font-size: 20pt;
  border-bottom: 3px solid #2563eb;
  padding-bottom: 8px;
  margin-top: 0;
  color: #1e3a8a;
}
h2 {
  font-size: 14pt;
  border-bottom: 1.5px solid #cbd5e1;
  padding-bottom: 4px;
  margin-top: 24px;
  color: #1e40af;
  page-break-after: avoid;
}
h3 {
  font-size: 12pt;
  margin-top: 18px;
  color: #1e3a8a;
  page-break-after: avoid;
}
h4 {
  font-size: 11pt;
  margin-top: 14px;
  color: #1f2937;
  page-break-after: avoid;
}
p { margin: 0.35em 0; }
ul, ol { margin: 0.35em 0; padding-left: 22px; }
li { margin: 1px 0; }
strong { color: #b91c1c; font-weight: 700; }
blockquote {
  border-left: 4px solid #2563eb;
  background: #eff6ff;
  margin: 10px 0;
  padding: 6px 12px;
  color: #1e3a8a;
  font-size: 10pt;
}
code {
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: "Consolas", "Courier New", monospace;
  font-size: 9.5pt;
  color: #b91c1c;
}
pre {
  background: #0f172a;
  color: #e2e8f0;
  padding: 10px 12px;
  border-radius: 6px;
  font-family: "Consolas", monospace;
  font-size: 9pt;
  line-height: 1.4;
  overflow-x: auto;
  page-break-inside: avoid;
}
pre code { background: none; color: inherit; padding: 0; font-size: 9pt; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
}
th, td {
  border: 1px solid #cbd5e1;
  padding: 5px 7px;
  text-align: left;
  vertical-align: top;
}
th {
  background: #1e40af;
  color: white;
  font-weight: 600;
}
tr:nth-child(even) td { background: #f8fafc; }
hr {
  border: none;
  border-top: 1.5px dashed #94a3b8;
  margin: 16px 0;
}
.mermaid {
  text-align: center;
  margin: 14px 0;
  page-break-inside: avoid;
}
.mermaid svg { max-width: 100%; height: auto !important; }
"""

# Mermaid 렌더링 부트스트랩. 모든 mermaid 블록이 렌더 끝나면
# document body 에 data-mermaid-ready=1 을 설정.
MERMAID_HEAD = r"""
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
window.addEventListener('load', async () => {
  if (typeof mermaid === 'undefined') {
    document.body.setAttribute('data-mermaid-ready', 'no-lib');
    return;
  }
  mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    flowchart: { htmlLabels: true, curve: 'basis' },
    securityLevel: 'loose',
  });
  try {
    await mermaid.run({ querySelector: '.mermaid' });
    document.body.setAttribute('data-mermaid-ready', '1');
  } catch (e) {
    document.body.setAttribute('data-mermaid-ready', 'err:' + (e.message || 'unknown'));
  }
});
</script>
"""


def md_to_html_body(md_text: str) -> str:
    """markdown → html. mermaid 코드 블록은 <div class="mermaid"> 로 치환."""
    # 마크다운 라이브러리 처리 전, ```mermaid ... ``` 를 미리 div로 치환
    def repl(match: re.Match) -> str:
        body = match.group(1)
        return f'\n<div class="mermaid">\n{body}\n</div>\n'

    md_text = re.sub(
        r"```mermaid\s*\n(.*?)```",
        repl,
        md_text,
        flags=re.DOTALL,
    )
    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )


def build_html(cover_html: str, body_html: str, title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{REPORT_CSS}</style>
{MERMAID_HEAD}
</head>
<body>
{cover_html}
{body_html}
</body>
</html>
"""


def render_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path) -> None:
    file_url = "file:///" + str(html_path).replace("\\", "/")
    cmd = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=20000",
        f"--print-to-pdf={pdf_path}",
        file_url,
    ]
    print(f"  Edge → PDF: {pdf_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if pdf_path.exists():
        size_kb = pdf_path.stat().st_size / 1024
        print(f"  OK {pdf_path.name} ({size_kb:.1f} KB)")
    else:
        print(f"  FAIL {pdf_path.name}")
        print(f"  stderr: {result.stderr[:500]}")
        sys.exit(1)


# -----------------------------------------------------------------------------
# Cover 생성
# -----------------------------------------------------------------------------
def cover(title: str, subtitle: str, version: str = "v0.11.x") -> str:
    today = time.strftime("%Y-%m-%d")
    return f"""
<div class="cover">
  <div class="badge">TK101 AI PLATFORM</div>
  <h1>{title}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="meta">
    <strong>버전</strong> {version}<br>
    <strong>발행일</strong> {today}<br>
    <strong>발행처</strong> TK101 Global Korea Inc. — 사내 AI 자동화 트랙<br>
    <strong>대상</strong> 대표·임원 보고 / 신규 개발자 온보딩 / 외주 파트너 인계
  </div>
</div>
"""


# -----------------------------------------------------------------------------
# 1. ARCHITECTURE 단독 PDF
# -----------------------------------------------------------------------------
def build_architecture_only() -> None:
    print("[1/3] ARCHITECTURE 단독 PDF")
    arch_md = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    body = md_to_html_body(arch_md)
    html = build_html(
        cover_html=cover(
            "시스템 구성 개요",
            "TK101 사내 AI 자동화 플랫폼 — 무엇을 만들었고 무엇을 더 만들 것인가",
        ),
        body_html=f'<div class="section">{body}</div>',
        title="TK101 AI — 시스템 구성 개요",
    )
    html_path = OUT / "ARCHITECTURE.html"
    pdf_path = OUT / "TK101_AI_Architecture.pdf"
    html_path.write_text(html, encoding="utf-8")
    render_pdf(html_path, pdf_path)


# -----------------------------------------------------------------------------
# 2. 통합 PDF (Architecture + Sitemap + Development Guide)
# -----------------------------------------------------------------------------
def build_combined() -> None:
    print("[2/3] 통합 PDF (ARCH+SITEMAP+GUIDE)")
    arch = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    sitemap = (DOCS / "SITEMAP.md").read_text(encoding="utf-8")
    guide = (DOCS / "DEVELOPMENT_GUIDE.md").read_text(encoding="utf-8")

    toc = """
<div class="toc">
  <h2>목차</h2>
  <ol>
    <li>시스템 구성 개요 (보고서용)
      <ul>
        <li>한 줄 요약 · 무엇을 하는 플랫폼인가</li>
        <li>시스템 구성 다이어그램 · 외부 노출 주소</li>
        <li>지금까지 만든 것 (T1~T9 라이브 현황)</li>
        <li>현재 만들고 있는 것 · 앞으로 만들 것</li>
        <li>권한 · 보안 정책 요약 · 알려진 한계</li>
      </ul>
    </li>
    <li>사이트맵 (보고서용)
      <ul>
        <li>화면 전체 지도 · 영역 5개</li>
        <li>부서별로 보이는 화면</li>
        <li>화면별 한 줄 설명</li>
        <li>진행 중 · 추가 예정 화면</li>
      </ul>
    </li>
    <li>개발 가이드 (개발자용)
      <ul>
        <li>로컬 환경 셋업 · 코드베이스 둘러보기</li>
        <li>개발 워크플로 · 코딩 컨벤션 · 테스트</li>
        <li>DB 마이그레이션 · 배포 운영</li>
        <li>신규 모듈 추가 체크리스트</li>
      </ul>
    </li>
  </ol>
</div>
"""

    body_parts = []
    for idx, (title, md) in enumerate(
        [
            ("Part 1. 시스템 구성 개요", arch),
            ("Part 2. 사이트맵", sitemap),
            ("Part 3. 개발 가이드", guide),
        ]
    ):
        body = md_to_html_body(md)
        body_parts.append(
            f'<div class="section"><h1>{title}</h1>{body}</div>'
        )

    html = build_html(
        cover_html=cover(
            "TK101 AI 플랫폼 종합 보고서",
            "아키텍처 · 사이트맵 · 개발 가이드 통합본",
        )
        + toc,
        body_html="\n".join(body_parts),
        title="TK101 AI — 종합 보고서",
    )
    html_path = OUT / "TK101_AI_Combined.html"
    pdf_path = OUT / "TK101_AI_종합보고서.pdf"
    html_path.write_text(html, encoding="utf-8")
    render_pdf(html_path, pdf_path)


# -----------------------------------------------------------------------------
# 3. 마스터 구성도 PNG (한 장)
# -----------------------------------------------------------------------------
MASTER_DIAGRAM_MERMAID = r"""
flowchart TB
  classDef user fill:#dbeafe,stroke:#1e3a8a,stroke-width:2px,color:#0f172a
  classDef edge fill:#fef3c7,stroke:#b45309,stroke-width:2px,color:#0f172a
  classDef app fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#0f172a
  classDef data fill:#fce7f3,stroke:#9d174d,stroke-width:2px,color:#0f172a
  classDef obs fill:#ede9fe,stroke:#5b21b6,stroke-width:2px,color:#0f172a
  classDef ext fill:#fee2e2,stroke:#991b1b,stroke-width:2px,color:#0f172a

  subgraph SUSER["① 사용자 접점"]
    direction LR
    U1["사내 직원<br/>브라우저"]:::user
    U2["관리자<br/>브라우저 + SSH"]:::user
  end

  subgraph SEDGE["② 엣지 (단일 진입점 :8080)"]
    NX["nginx<br/>(frontend container)<br/>정적자산 + /api, /n8n/ 프록시"]:::edge
  end

  subgraph SAPP["③ 애플리케이션 레이어"]
    direction TB
    FE["React 18 + Vite<br/>Ant Design SPA<br/>📍 사이드바 권한 게이트"]:::app
    BE["FastAPI + SQLAlchemy 2 async<br/>📍 라우터 18개<br/>JWT + httpOnly cookie · RBAC"]:::app
    N8["n8n<br/>워크플로 자동화<br/>📍 127.0.0.1 내부전용"]:::app
    OW["Open WebUI :3000<br/>사외 AI 시범<br/>📍 가입 승인제"]:::app
  end

  subgraph SDATA["④ 데이터 레이어"]
    direction LR
    PG[("PostgreSQL 16 + pgvector<br/>📍 9개 마이그레이션")]:::data
    NAS[("사내 NAS<br/>📍 SSHFS read-only")]:::data
    HF[("HuggingFace 캐시<br/>multilingual-e5-large")]:::data
    FF[("form_filler 산출물<br/>persistent volume")]:::data
  end

  subgraph SOBS["⑤ 관측 · 운영"]
    LF["Langfuse :3001<br/>LLM 호출/비용 추적<br/>📍 127.0.0.1 내부전용"]:::obs
  end

  subgraph SEXT["⑥ 외부 AI · 데이터 통합"]
    direction LR
    AN["Anthropic Claude<br/>Sonnet · Haiku · Opus"]:::ext
    TC["Tencent MaaS<br/>OpenAI-compat + MPS AIGC<br/>📍 23개 모델"]:::ext
    YT["YouTube Data API"]:::ext
  end

  subgraph TRACKS["■ 비즈니스 트랙 (라이브 운영 중)"]
    direction LR
    T1["T1 회계 자동화 v0.9<br/>6개 은행 엑셀 임포트<br/>매칭·세금계산서"]:::app
    T4["T4 NAS 자료 검색<br/>의미 검색 + 필터"]:::app
    T5["T5 양식 자동작성<br/>analyzer · mapper · render"]:::app
    T6["T6 체험단 번역<br/>중→한, Haiku 4.5"]:::app
    T2["T2 SNS 마케팅<br/>YouTube 일일 수집"]:::app
    T8["T8 AI Playground<br/>admin · 8공급자 23모델"]:::app
    T9["T9 신사업유통<br/>4회사 + 텔레그램 다계정 대화"]:::app
  end

  U1 --> NX
  U2 --> NX
  NX --> FE
  FE -- "JSON · SSE" --> BE
  NX -- "auth_request 가드" --> N8
  U1 -- ":3000" --> OW

  BE --> PG
  BE -- ":ro bind" --> NAS
  BE --> HF
  BE --> FF
  BE -- "trace" --> LF
  BE --> AN
  BE --> TC
  BE --> YT
  N8 --> BE
  N8 --> AN
  OW --> AN
  OW --> PG

  BE -.운영.-> TRACKS

  style SUSER fill:#eff6ff,stroke:#1e3a8a,stroke-width:2px
  style SEDGE fill:#fffbeb,stroke:#b45309,stroke-width:2px
  style SAPP fill:#f0fdf4,stroke:#15803d,stroke-width:2px
  style SDATA fill:#fdf2f8,stroke:#9d174d,stroke-width:2px
  style SOBS fill:#f5f3ff,stroke:#5b21b6,stroke-width:2px
  style SEXT fill:#fef2f2,stroke:#991b1b,stroke-width:2px
  style TRACKS fill:#f8fafc,stroke:#475569,stroke-width:2px,stroke-dasharray: 5 5
"""

MASTER_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>TK101 AI - 마스터 구성도</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Malgun Gothic", "맑은 고딕", -apple-system, "Segoe UI", sans-serif;
    background: white;
    padding: 28px 36px;
    width: 2200px;
  }
  .head {
    border-bottom: 4px solid #1e3a8a;
    padding-bottom: 12px;
    margin-bottom: 18px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .head h1 {
    font-size: 30pt;
    color: #1e3a8a;
    letter-spacing: -0.5px;
  }
  .head .meta {
    color: #475569;
    font-size: 13pt;
    text-align: right;
    line-height: 1.5;
  }
  .head .meta strong { color: #1e40af; }
  .subtitle {
    font-size: 14pt;
    color: #475569;
    margin-bottom: 14px;
  }
  .diagram {
    background: white;
    padding: 8px;
    border-radius: 8px;
  }
  .diagram svg { width: 100% !important; height: auto !important; max-width: 100% !important; }
  .footer {
    margin-top: 24px;
    border-top: 1.5px dashed #94a3b8;
    padding-top: 12px;
    color: #64748b;
    font-size: 11pt;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .footer .legend { display: flex; gap: 18px; flex-wrap: wrap; }
  .footer .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .footer .legend i {
    width: 16px; height: 16px; border-radius: 3px; display: inline-block;
    border: 2px solid currentColor;
  }
  .c-user { color: #1e3a8a; }
  .c-edge { color: #b45309; }
  .c-app  { color: #15803d; }
  .c-data { color: #9d174d; }
  .c-obs  { color: #5b21b6; }
  .c-ext  { color: #991b1b; }
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
  window.addEventListener('load', async () => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      flowchart: { htmlLabels: true, curve: 'basis', useMaxWidth: false },
      securityLevel: 'loose',
    });
    try {
      await mermaid.run({ querySelector: '.mermaid' });
      document.body.setAttribute('data-mermaid-ready', '1');
    } catch (e) {
      document.body.setAttribute('data-mermaid-ready', 'err');
    }
  });
</script>
</head>
<body>
  <div class="head">
    <div>
      <h1>TK101 AI 플랫폼 — 전체 구성도</h1>
      <div class="subtitle">사용자 → 엣지 → 애플리케이션 → 데이터 → 외부 AI · 운영 한 장</div>
    </div>
    <div class="meta">
      <strong>버전</strong> v0.11.x<br>
      <strong>발행</strong> __DATE__<br>
      <strong>호스트</strong> 43.155.202.112
    </div>
  </div>
  <div class="diagram">
    <div class="mermaid">
__MERMAID__
    </div>
  </div>
  <div class="footer">
    <div class="legend">
      <span class="c-user"><i></i>① 사용자</span>
      <span class="c-edge"><i></i>② 엣지(nginx)</span>
      <span class="c-app"><i></i>③ 애플리케이션</span>
      <span class="c-data"><i></i>④ 데이터</span>
      <span class="c-obs"><i></i>⑤ 관측</span>
      <span class="c-ext"><i></i>⑥ 외부 AI</span>
    </div>
    <div>TK101 Global Korea Inc. · 사내 AI 자동화 트랙</div>
  </div>
</body>
</html>
"""


def build_master_diagram() -> None:
    print("[3/3] 마스터 구성도 PNG")
    today = time.strftime("%Y-%m-%d")
    html = (
        MASTER_HTML_TEMPLATE
        .replace("__MERMAID__", MASTER_DIAGRAM_MERMAID)
        .replace("__DATE__", today)
    )
    html_path = OUT / "TK101_AI_Master.html"
    png_path = OUT / "TK101_AI_전체구성도.png"
    html_path.write_text(html, encoding="utf-8")

    file_url = "file:///" + str(html_path).replace("\\", "/")
    cmd = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1.5",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=15000",
        "--window-size=2400,1800",
        f"--screenshot={png_path}",
        file_url,
    ]
    print(f"  Edge → PNG: {png_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if png_path.exists():
        size_kb = png_path.stat().st_size / 1024
        print(f"  OK {png_path.name} ({size_kb:.1f} KB)")
    else:
        print(f"  FAIL {png_path.name}")
        print(f"  stderr: {result.stderr[:500]}")
        sys.exit(1)


# -----------------------------------------------------------------------------
# 4. AUDIT 요약 PDF (보고서용 핵심 정리)
# -----------------------------------------------------------------------------
def build_audit_summary() -> None:
    print("[4/5] AUDIT 요약 PDF (점검 보고서)")
    md_path = DOCS / "AUDIT_SUMMARY_2026-05-19.md"
    if not md_path.exists():
        print(f"  SKIP — {md_path.name} 없음")
        return
    md = md_path.read_text(encoding="utf-8")
    body = md_to_html_body(md)
    html = build_html(
        cover_html=cover(
            "종합 점검 보고서",
            "TK101 사내 AI 자동화 플랫폼 — 5트랙 병렬 점검 결과 (2026-05-19)",
        ),
        body_html=f'<div class="section">{body}</div>',
        title="TK101 AI — 종합 점검 보고서",
    )
    html_path = OUT / "AUDIT_SUMMARY.html"
    pdf_path = OUT / "TK101_AI_점검보고서.pdf"
    html_path.write_text(html, encoding="utf-8")
    render_pdf(html_path, pdf_path)


# -----------------------------------------------------------------------------
# 5. STRATEGY PDF (다음 라운드 방향성)
# -----------------------------------------------------------------------------
def build_strategy() -> None:
    print("[5/5] STRATEGY PDF (방향성 제안)")
    md_path = DOCS / "STRATEGY_2026-05-19.md"
    if not md_path.exists():
        print(f"  SKIP — {md_path.name} 없음")
        return
    md = md_path.read_text(encoding="utf-8")
    body = md_to_html_body(md)
    html = build_html(
        cover_html=cover(
            "다음 라운드 방향성 제안",
            "사용자 메모 + 종합 점검 결과 연계 분석 (2026-05-19)",
        ),
        body_html=f'<div class="section">{body}</div>',
        title="TK101 AI — 방향성 제안",
    )
    html_path = OUT / "STRATEGY.html"
    pdf_path = OUT / "TK101_AI_방향성제안.pdf"
    html_path.write_text(html, encoding="utf-8")
    render_pdf(html_path, pdf_path)


# -----------------------------------------------------------------------------
# 6. DISCUSSION PDF (회의 논의 자료)
# -----------------------------------------------------------------------------
def build_discussion() -> None:
    print("[6/6] DISCUSSION PDF (회의 논의 자료)")
    md_path = DOCS / "cost" / "DISCUSSION_2026-05-20.md"
    if not md_path.exists():
        print(f"  SKIP — {md_path.name} 없음")
        return
    md = md_path.read_text(encoding="utf-8")
    body = md_to_html_body(md)
    html = build_html(
        cover_html=cover(
            "향후 검토 필요 사항",
            "회의 논의 자료 — 보안 · 텐센트 AI · 비용 · 추가 고려 (2026-05-20)",
        ),
        body_html=f'<div class="section">{body}</div>',
        title="TK101 AI — 회의 논의 자료",
    )
    html_path = OUT / "DISCUSSION.html"
    pdf_path = OUT / "TK101_AI_회의논의자료.pdf"
    html_path.write_text(html, encoding="utf-8")
    render_pdf(html_path, pdf_path)


# -----------------------------------------------------------------------------
# 7. COST SIMULATION PDF (비용 시뮬레이션 자료)
# -----------------------------------------------------------------------------
def build_cost_simulation() -> None:
    print("[7/7] COST SIMULATION PDF (비용 시뮬레이션)")
    md_path = DOCS / "cost" / "COST_SIMULATION_2026-05-20.md"
    if not md_path.exists():
        print(f"  SKIP — {md_path.name} 없음")
        return
    md = md_path.read_text(encoding="utf-8")
    body = md_to_html_body(md)
    html = build_html(
        cover_html=cover(
            "AI Playground 비용 시뮬레이션",
            "회의 자료 — 사용자·모델별 월 비용 추정 + 절감 레버 (2026-05-20)",
        ),
        body_html=f'<div class="section">{body}</div>',
        title="TK101 AI — 비용 시뮬레이션",
    )
    html_path = OUT / "COST_SIMULATION.html"
    pdf_path = OUT / "TK101_AI_비용시뮬레이션.pdf"
    html_path.write_text(html, encoding="utf-8")
    render_pdf(html_path, pdf_path)


# -----------------------------------------------------------------------------
def main() -> None:
    print(f"[빌드 시작] 출력 폴더: {OUT}")
    if len(sys.argv) > 1 and sys.argv[1] == "discussion":
        build_discussion()
        print(f"\n산출물 위치: {OUT}")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "cost":
        build_cost_simulation()
        print(f"\n산출물 위치: {OUT}")
        return
    build_architecture_only()
    build_combined()
    build_master_diagram()
    build_audit_summary()
    build_strategy()
    build_discussion()
    build_cost_simulation()
    print()
    print("=" * 60)
    print(f"산출물 위치: {OUT}")
    for p in sorted(OUT.iterdir()):
        if p.suffix.lower() in {".pdf", ".png"}:
            print(f"  - {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
