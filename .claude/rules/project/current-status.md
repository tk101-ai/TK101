# 현재 진행 상태

> CLAUDE.md §5에서 참조. 작업 진행 시 이 파일을 업데이트하세요.
> 세션 시작 시 `/bkit:pdca status`와 함께 확인.

**최종 업데이트**: 2026-04-16

---

## 현재 작업

- **현재 feature**: `tk101-platform-foundation` (1단계 뼈대 구축)
- **PDCA 단계**: Do 진행 중 — **skeleton scope 완료**
- **다음 scope**: `domain-db` (Entity + Repository 인터페이스 + SQLAlchemy 모델 + 첫 Alembic 마이그레이션)

## Sprint 체크리스트

### 완료

- [x] Plan 문서 작성 (2026-04-16)
- [x] Design 문서 작성 — Clean Architecture 선택 (2026-04-16)
- [x] CLAUDE.md + 분리 규칙 파일 작성 (2026-04-16)
- [x] **Sprint 0 — skeleton scope 완료** (2026-04-16, 58 파일 생성)
  - Clean Architecture 4 레이어 디렉터리 전부 구축
  - FastAPI 앱 + /health 엔드포인트
  - Next.js 15 + App Router + Tailwind + shadcn 베이스
  - Docker Compose (dev + prod)
  - Alembic 초기화
  - GitHub Actions CI 기본 구조

### 진행 예정

- [ ] **Sprint 0 — domain-db scope** — Entity + Repository 인터페이스 + ORM 모델 + 첫 마이그레이션
- [ ] **Sprint 1**: auth + dashboard-shell + cicd (4/19~4/25)
- [ ] **4/21 월요일 이사님 미팅** — 아키텍처 + 로그인 + CI/CD 시연
- [ ] **Sprint 2**: admin-crud + chat + security (4/26~5/9)
- [ ] 뼈대 완성 (5/9 목표)
- [ ] 2단계 회계 모듈 Plan 착수 (5/10~)

## 알려진 미결정 사항

- ~~Python 패키지 매니저~~: **uv 확정** (2026-04-16)
- 잔디 유지 vs 슬랙 전환 (3단계에서 결정)
- NAS 외부 접근 가능 여부 (3단계 전 확인)

## 인프라 현황

- Tencent CVM 4vCPU/8GB: 생성 완료
- GitHub 레포: 생성 완료, 로컬 git 연결됨
- GitHub Actions → CVM CD: **미설정** (Sprint 1에서 구축)

## 참조 문서 (빠른 링크)

### 현재 feature PDCA
- Plan: `docs/01-plan/features/tk101-platform-foundation.plan.md`
- Design: `docs/02-design/features/tk101-platform-foundation.design.md`

### 프로젝트 규칙
- 도구 분담: `.claude/rules/project/tool-split.md`
- 표준 플로우: `.claude/rules/project/workflow.md`
- 명령어: `.claude/rules/project/commands-cheatsheet.md`

### 초기 기획
- 플랫폼 구조: `PROJECT_DESIGN.md`
- 기술 검토: `초기설정 구성방안/기술스택_및_환경검토.md`
- bkit+ECC 전략: `초기설정 구성방안/ECC_bkit_병행사용_전략.md`
