# TK101 AI Platform — CLAUDE.md

> 매 세션 자동 로드. 짧게 유지. 상세 내용은 필요할 때 링크된 파일을 Read로 조회.
> **최종 업데이트**: 2026-04-16

---

## 1. 프로젝트 한 줄 정의

40명 규모 TK101 사내 AI 자동화 플랫폼. 1인 담당자 + Claude Code로 구축/유지보수.
**현재 단계**: Sprint 0 착수 직전 (Plan/Design 완료, Clean Architecture 확정).

---

## 2. 절대 규칙 (위반 시 차단)

### 2.1 Clean Architecture Import 규칙 (Backend)

| 레이어 | Import 가능 | Import 금지 |
|-------|-----------|-----------|
| Presentation | Application, Domain | Infrastructure 직접 (DI로만) |
| Application | Domain | Presentation, Infrastructure 구현체 |
| **Domain** | **외부 의존성 0** | **FastAPI, SQLAlchemy, pydantic 모두 금지** |
| Infrastructure | Domain | Application, Presentation |

### 2.2 코드 품질 하드 리밋

- 함수 ≤ 50줄, 파일 ≤ 400줄(800 절대 상한), 중첩 ≤ 4단계
- Entity는 `@dataclass(frozen=True)` (불변)
- Repository 반환은 Domain Entity만 (SQLAlchemy 모델 유출 금지)
- hardcoded secrets 금지 / `any` 타입 금지 / `print()` 디버그 금지

### 2.3 보안 필수 (인증·권한·외부 입력 변경 시)

- 반드시 ECC `security-reviewer` 호출
- 모든 사용자 입력: Pydantic/Zod 검증
- 비밀번호: bcrypt (cost 12)
- JWT: HS256, access 30분 / refresh 14일

**상세 코딩 규칙**: `.claude/rules/common/coding-style.md`, `.claude/rules/common/security.md`

---

## 3. 작업 라우팅 테이블 (핵심)

> **요청이 들어오면 여기서 먼저 매핑 → 해당 파일만 Read.**
> 전체 내용을 외우려 하지 말 것. 필요한 것만 Just-in-Time 로드.

| 사용자 요청 유형 | 먼저 읽을 파일 | 사용할 도구 |
|---|---|---|
| "새 기능 기획하고 싶어" | `.claude/rules/project/workflow.md` §A | `/bkit:pdca plan <feature>` |
| "설계해줘" / "아키텍처 고민" | 해당 feature Plan + `docs/02-design/features/tk101-platform-foundation.design.md` §2, §9 | `/bkit:pdca design <feature>` |
| "구현 시작" / "코드 작성" | 해당 feature Design (전체) + `workflow.md` §B | `/bkit:pdca do <feature> --scope X` |
| "TDD로 테스트부터" | Design §8 Test Plan + `.claude/rules/common/testing.md` | `/tdd <feature>` |
| "FastAPI 코드 리뷰" | `.claude/rules/common/code-review.md` | ECC `python-reviewer` (자동) |
| "Next.js/React 작업" | `.claude/rules/web/` 전체 | ECC `typescript-reviewer` (자동) |
| "DB 스키마/쿼리" | Design §3 + `.claude/skills/postgres-patterns/` | ECC `database-reviewer` |
| "인증/보안 코드" | `.claude/rules/common/security.md` | ECC `security-reviewer` (**필수**) |
| "빌드 에러 났어" | 에러 메시지 + 해당 파일 | ECC `build-error-resolver` |
| "bkit vs ECC 뭐 써?" | `.claude/rules/project/tool-split.md` | - |
| "명령어 까먹었어" | `.claude/rules/project/commands-cheatsheet.md` | - |
| "Docker/배포" | `.claude/skills/docker-patterns/`, `.claude/skills/github-ops/` | ECC `docker-patterns`, `github-ops` |
| "QA 시작" | Design §8 | `/bkit:qa-phase <feature>` |
| "설계랑 구현 비교" | Design 전체 | `/bkit:pdca analyze <feature>` |
| "완료 보고서" | Plan + Design + Analysis | `/bkit:pdca report <feature>` |
| "회계 모듈 시작" | `PROJECT_DESIGN.md` §회계 + `초기설정 구성방안/ECC_bkit_병행사용_전략.md` §2단계 | `/bkit:pdca plan accounting-automation` |
| "잔디/메신저 연동" | `초기설정 구성방안/AI_자동화_인프라_메모.md` §잔디 API | 3단계 작업, 지금은 보류 |
| "멀티 AI (OpenAI/Gemini)" | Design §9.4 LLMProvider 섹션 | 3단계, `LLMProvider` 인터페이스 확장 |
| "세션 뭐부터 시작?" | 이 파일 §5 현재 상태 + `/bkit:pdca status` | - |

---

## 4. 세션 시작 3단계 체크리스트

모든 새 세션에서 자동 실행:

1. **이 파일(CLAUDE.md) 확인** — 자동 로드됨
2. **현재 진행 중인 feature Design 확인** — §5의 "현재 feature"에 따라 Read
3. **`/bkit:pdca status` 실행** — PDCA 단계와 Task 상태 확인

그 다음 사용자 요청을 §3 라우팅 테이블과 매핑.

---

## 5. 현재 진행 상태

**현재 feature**: `tk101-platform-foundation` (1단계 뼈대)
**현재 단계**: Do 진행 중 — `skeleton` scope 완료 (58 파일) / 다음 `domain-db`
**Python 매니저**: uv 확정

상세 체크리스트 및 미결정 사항: `.claude/rules/project/current-status.md`

---

## 6. 참조 문서 맵

### PDCA 문서 (현재 feature)

- Plan: `docs/01-plan/features/tk101-platform-foundation.plan.md`
- Design: `docs/02-design/features/tk101-platform-foundation.design.md`

### 프로젝트 규칙 (이 폴더 안)

- 도구 분담: `.claude/rules/project/tool-split.md`
- 표준 플로우: `.claude/rules/project/workflow.md`
- 명령어: `.claude/rules/project/commands-cheatsheet.md`

### ECC 공통 규칙

- 코딩 스타일: `.claude/rules/common/coding-style.md`
- 테스트: `.claude/rules/common/testing.md`
- 보안: `.claude/rules/common/security.md`
- 코드 리뷰: `.claude/rules/common/code-review.md`
- 웹 규칙: `.claude/rules/web/`

### 초기 기획 문서

- 플랫폼 구조: `PROJECT_DESIGN.md`
- 기술 검토: `초기설정 구성방안/기술스택_및_환경검토.md`
- bkit+ECC 전략: `초기설정 구성방안/ECC_bkit_병행사용_전략.md`
- 인프라 메모: `초기설정 구성방안/AI_자동화_인프라_메모.md`

---

## 7. 기술 스택 (1줄씩)

- Backend: FastAPI (Python 3.12+, async)
- Frontend: Next.js 15 (App Router, TS) + Tailwind + shadcn/ui
- DB: PostgreSQL 16 + Redis
- ORM: SQLAlchemy 2.0 async + Alembic
- 상태: TanStack Query (서버) + Zustand (클라이언트)
- 테스트: pytest + Playwright
- 배포: Docker Compose + GitHub Actions → Tencent CVM

**상세**: Design 문서 §1.2, §9

---

## 8. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-04-16 | 초안 + 슬림화 (350줄 → 약 150줄, Router Pattern 적용) |
