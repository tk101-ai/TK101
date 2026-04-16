# TK101 플랫폼 뼈대 구축 Planning Document

> **Summary**: 40명 규모 사내 AI 자동화 플랫폼의 서버/DB/인증/기본UI/CI/CD 뼈대 구축
>
> **Project**: TK101 사내 AI 자동화 플랫폼
> **Version**: 0.1.0
> **Author**: TK101 (junki7853)
> **Date**: 2026-04-16
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 40명 직원의 업무 자동화 인프라가 없음. AI API 키는 보유했으나 이를 안전하게 활용할 플랫폼이 부재. 1인 담당자가 유지보수 가능한 구조 필요. |
| **Solution** | FastAPI + Next.js + PostgreSQL 기반 3레이어 플랫폼을 Docker Compose로 Tencent CVM에 배포. GitHub Actions CI/CD 자동화. |
| **Function/UX Effect** | 직원: 웹에서 로그인 후 AI 대화 가능. 관리자: 사용자/권한/부서 관리 백오피스. 부서별 권한 분리로 데이터 접근 통제. |
| **Core Value** | 회계 자동화를 비롯한 모든 후속 모듈의 기반이 되는 안전한 인프라. 1인 유지보수 구조 + Claude Code 친화적 설계로 빠른 확장 가능. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | AI API는 보유했으나 직원들이 안전하게 사용할 플랫폼이 없음. 회계 자동화(이사님 요청)의 기반 인프라 필요. |
| **WHO** | 1차: 관리자(TK101) — 플랫폼 세팅 및 운영. 2차: 전 직원 40명 — AI 업무 요청. 3차: 이사님 — 회계 자동화 결과 확인. |
| **RISK** | 1인 개발자 병목. Clean Architecture 초기 세팅 3~5일 소요. CVM 단일 서버 장애 시 전체 서비스 중단. |
| **SUCCESS** | (1) 로그인+대시보드 접속 가능 (2) 부서별 권한 분리 동작 (3) CI/CD로 코드 push 시 자동 배포 (4) Docker Compose로 서비스 일괄 관리 (5) **Clean Architecture 4 레이어 유지 + 테스트 커버리지 80%+** |
| **SCOPE** | 1단계 뼈대만. 회계 모듈/카카오톡/멀티AI/NAS는 2~3단계에서 별도 PDCA로 진행. |

---

## 1. Overview

### 1.1 Purpose

TK101 Global Korea Inc. 사내 AI 자동화 플랫폼의 기반 인프라를 구축한다.
서버, DB, 인증, 기본 웹 UI, CI/CD 파이프라인을 포함하며, 이후 회계 자동화 등 모든 업무 모듈이 이 뼈대 위에 탑재된다.

### 1.2 Background

- 대표 방향: Claude 에이전트 기반 병렬 자동화
- 담당자 방향: 인프라 구축 우선 → 모듈 순차 탑재
- 이사님 요청: 회계 자동화 최우선 → 뼈대 빠른 완성 필요
- 직원 40명 중 IT 종사자 거의 없음 → 단순하고 직관적인 UI 필수
- **다음주 월요일(4/21) 미팅**: 시연 가능한 성과 필요

### 1.3 Related Documents

- 프로젝트 설계: `PROJECT_DESIGN.md`
- 기술 스택 검토: `초기설정 구성방안/기술스택_및_환경검토.md`
- ECC+bkit 전략: `초기설정 구성방안/ECC_bkit_병행사용_전략.md`
- 인프라 메모: `초기설정 구성방안/AI_자동화_인프라_메모.md`

---

## 2. Scope

### 2.1 In Scope

- [x] Tencent CVM 서버 환경 구성 (Docker, Docker Compose)
- [ ] PostgreSQL DB 설계 및 구축 (사용자, 부서, 권한 테이블)
- [ ] FastAPI 백엔드 기본 구조 (인증, RBAC, 헬스체크 API)
- [ ] Next.js 프론트엔드 기본 구조 (로그인, 대시보드 쉘, 백오피스 쉘)
- [ ] JWT 기반 인증 + 부서별/직급별 권한 체계
- [ ] Docker Compose 구성 (FastAPI + PostgreSQL + Redis)
- [ ] GitHub Actions → Tencent CVM 자동 배포 (CD)
- [ ] Claude API 기본 연동 (헬스체크 + 간단한 대화 엔드포인트)
- [ ] 환경변수 관리 (.env + GitHub Secrets)

### 2.2 Out of Scope

- 회계 자동화 모듈 (2단계 별도 PDCA)
- 카카오톡/메신저 연동 (3단계)
- 멀티 AI 추상화 레이어 (3단계)
- NAS 연동 (3단계, 외부 접근 확인 후)
- 고급 모니터링/로깅 (운영 단계)
- 마케팅 업무 자동화 테스트 (즉시 테스트 우선순위 작업은 별도)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 사용자 로그인/로그아웃 (이메일+비밀번호, JWT) | High | Pending |
| FR-02 | 부서(5개) 및 직급별 권한 분리 (일반/팀장/관리자) | High | Pending |
| FR-03 | 사용자/부서/권한 CRUD 백오피스 API | High | Pending |
| FR-04 | 기본 대시보드 UI (로그인 후 랜딩) | High | Pending |
| FR-05 | 백오피스 UI (사용자 관리, 부서 관리) | High | Pending |
| FR-06 | Claude API 기본 대화 엔드포인트 (/api/chat) | Medium | Pending |
| FR-07 | 모델 라우팅 (Haiku 기본, Sonnet/Opus 선택 가능) | Medium | Pending |
| FR-08 | API 요청/응답 이력 저장 (PostgreSQL JSON 컬럼) | Medium | Pending |
| FR-09 | 부서별 API 사용량 추적 (월별 토큰 카운트) | Low | Pending |
| FR-10 | 헬스체크 엔드포인트 (/health) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | API 응답 시간 < 500ms (Claude API 제외) | FastAPI 미들웨어 로깅 |
| Security | JWT 토큰 기반 인증, RBAC 권한 검증 | security-reviewer 에이전트 |
| Security | 비밀번호 bcrypt 해싱, HTTPS 적용 | 코드 리뷰 |
| Availability | Docker Compose restart policy: always | docker-compose.yml 설정 |
| Maintainability | 1인 유지보수 가능한 모듈 구조 | 파일당 < 400줄, 함수당 < 50줄 |
| Scalability | 40명 동시 접속 처리 | uvicorn workers 설정 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 직원이 웹 브라우저에서 로그인하여 대시보드 접근 가능
- [ ] 관리자가 백오피스에서 사용자/부서 CRUD 가능
- [ ] 부서별 권한 분리 동작 확인 (A부서 사용자가 B부서 데이터 접근 불가)
- [ ] Claude API로 간단한 대화 가능 (/api/chat 엔드포인트)
- [ ] `git push` 시 GitHub Actions가 자동으로 CVM에 배포
- [ ] Docker Compose로 전체 서비스 일괄 시작/중지 가능

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상 (백엔드 핵심 로직)
- [ ] 보안 리뷰 통과 (hardcoded secrets 없음, SQL injection 방지)
- [ ] API 문서 자동 생성 (FastAPI Swagger UI)
- [ ] 빌드 에러 없이 Docker 이미지 생성

### 4.3 미팅 시연 목표 (4/21 월요일, Sprint 1 중간 시점)

Clean Architecture 세팅 우선으로 전체 기능은 Sprint 1 말(4/25)에 완성 예정. 4/21에는 아래 수준의 진척을 시연.

- [ ] 아키텍처 다이어그램 발표 (Clean Architecture 4 레이어 + 확장성 설명)
- [ ] Docker Compose 실행 시연 (`docker compose up`으로 전체 스택 기동)
- [ ] GitHub Actions 동작 시연 (코드 push → CVM 자동 배포 로그)
- [ ] 로그인 페이지 데모 (로그인 성공 → 대시보드 빈 쉘 진입)
- [ ] Health 엔드포인트 (`/health` 200 OK 확인)
- [ ] **Key Message**: "견고한 설계에 투자하여 5개 팀 모듈을 안정적으로 올릴 기반 구축 중. AI 채팅 기능은 Sprint 2(4/26~5/9), 회계 자동화는 5월 중순 완성 예정."

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 1인 개발자 병목 (4일 내 완성 압박) | High | High | MVP 범위 최소화. UI는 기능 위주, 디자인은 2차. bkit+ECC 병행으로 속도 확보. |
| CVM 단일 서버 장애 | Medium | Low | Docker Compose restart policy + 일일 DB 백업 스크립트. 2단계에서 이중화 검토. |
| 비개발자 직원의 낮은 기술 이해도 | Medium | High | 직관적 UI. 로그인 외 복잡한 설정 없이 사용 가능한 구조. |
| Claude API 비용 초과 | Medium | Medium | 모델 라우팅(Haiku 80%), 부서별 사용량 추적, 월별 한도 설정(2단계). |
| GitHub Secrets / API 키 유출 | High | Low | .env는 .gitignore, 서버 환경변수로 관리. security-reviewer로 커밋 전 스캔. |
| Tencent CVM 네트워크 지연 (중국 리전) | Low | Medium | 한국 리전 선택 확인. CDN은 3단계에서 검토. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| Tencent CVM 서버 | Infrastructure | Docker, Docker Compose 설치. 방화벽 포트 오픈 (80, 443, 8000) |
| GitHub Repository | CI/CD | GitHub Actions workflow 파일 추가. Secrets에 CVM 접속 정보 등록 |
| 신규 PostgreSQL DB | Database | users, departments, roles, chat_history 테이블 생성 |

### 6.2 Current Consumers

신규 프로젝트이므로 기존 소비자 없음. 향후 2단계 회계 모듈이 이 뼈대의 첫 번째 소비자가 됨.

| Resource | Future Consumer | Notes |
|----------|----------------|-------|
| users 테이블 | 회계 모듈 (2단계) | 작업 요청자 식별에 사용 |
| auth API | 모든 후속 모듈 | JWT 토큰으로 인증 |
| Docker Compose | 회계 모듈 서비스 추가 | 컨테이너 추가 용이한 구조 필요 |

### 6.3 Verification

- [ ] DB 스키마가 향후 회계 모듈 확장에 적합한지 검토
- [ ] API 라우팅 구조가 모듈 추가에 유연한지 검토
- [ ] Docker Compose가 서비스 추가에 용이한지 검토

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites, portfolios | |
| **Dynamic** | Feature-based modules, BaaS integration | Web apps with backend, SaaS MVPs | **V** |
| **Enterprise** | Strict layer separation, DI, microservices | High-traffic systems | |

**선택 이유**: 40명 규모 사내 플랫폼. 마이크로서비스는 과도하고 Starter는 부족. Feature-based 모듈 구조로 회계/마케팅 등 모듈을 순차 추가하는 Dynamic 레벨이 적합.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 백엔드 | FastAPI / Django / Express | **FastAPI** | AI 라이브러리 생태계, Claude Code Python 생성 품질, Pydantic 자체 문서화 |
| 프론트엔드 | Next.js / React SPA / Vue | **Next.js (App Router)** | SSR, 미들웨어, API Routes 내장. 채팅UI+백오피스 하나로 관리 |
| DB | PostgreSQL / MySQL / SQLite | **PostgreSQL** | JSON 타입(AI 응답 저장), pgvector(향후 RAG), 트랜잭션 안정성 |
| 캐시/큐 | Redis / 없음 | **Redis** | 세션 캐시, API 응답 캐시, 향후 작업 큐 |
| 인증 | JWT / Session | **JWT (access+refresh)** | 프론트-백 분리 구조, 모바일 확장 대비 |
| ORM | SQLAlchemy / Tortoise / Raw SQL | **SQLAlchemy 2.0** | 타입 힌트, async 지원, 마이그레이션(Alembic) |
| CSS | Tailwind / CSS Modules / shadcn | **Tailwind + shadcn/ui** | 빠른 UI 구축, 컴포넌트 재사용 |
| 테스트 | pytest / unittest | **pytest + httpx** | FastAPI 공식 권장, async 테스트 지원 |
| 배포 | Docker Compose / K8s | **Docker Compose** | 40명 규모에 K8s는 과도. 단일 서버 Docker Compose로 충분. |

### 7.3 Clean Architecture Approach

```
Selected Level: Dynamic

프로젝트 구조:
┌─────────────────────────────────────────────────────────┐
│ backend/ (FastAPI)                                       │
│   ├── app/                                               │
│   │   ├── main.py              # FastAPI 앱 진입점       │
│   │   ├── config.py            # 환경변수, 설정          │
│   │   ├── database.py          # DB 연결, 세션           │
│   │   ├── models/              # SQLAlchemy 모델         │
│   │   │   ├── user.py                                    │
│   │   │   ├── department.py                              │
│   │   │   └── chat_history.py                            │
│   │   ├── schemas/             # Pydantic 스키마         │
│   │   ├── routers/             # API 라우터              │
│   │   │   ├── auth.py          # 로그인/로그아웃         │
│   │   │   ├── users.py         # 사용자 CRUD            │
│   │   │   ├── departments.py   # 부서 CRUD              │
│   │   │   └── chat.py          # Claude API 대화        │
│   │   ├── services/            # 비즈니스 로직           │
│   │   ├── middleware/          # 인증, CORS, 로깅        │
│   │   └── utils/               # 유틸리티               │
│   ├── alembic/                 # DB 마이그레이션         │
│   ├── tests/                   # pytest 테스트           │
│   ├── Dockerfile                                         │
│   └── requirements.txt                                   │
├─────────────────────────────────────────────────────────┤
│ frontend/ (Next.js)                                      │
│   ├── src/                                               │
│   │   ├── app/                 # App Router 페이지       │
│   │   │   ├── (auth)/          # 로그인 그룹            │
│   │   │   ├── dashboard/       # 대시보드               │
│   │   │   └── admin/           # 백오피스               │
│   │   ├── components/          # 공용 컴포넌트           │
│   │   ├── lib/                 # API 클라이언트 등       │
│   │   └── types/               # TypeScript 타입         │
│   ├── Dockerfile                                         │
│   └── package.json                                       │
├─────────────────────────────────────────────────────────┤
│ docker-compose.yml             # 전체 서비스 오케스트라  │
│ .github/workflows/deploy.yml   # CI/CD                   │
│ .env.example                   # 환경변수 템플릿         │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [ ] `CLAUDE.md` has coding conventions section — **없음, 생성 필요**
- [ ] `docs/01-plan/conventions.md` exists — **없음, 이번에 생성**
- [x] `.claude/rules/` 규칙 파일 — **ECC 규칙 적용 중**
- [ ] ESLint configuration — **없음, 프론트엔드 세팅 시 생성**
- [ ] Prettier configuration — **없음, 프론트엔드 세팅 시 생성**
- [ ] TypeScript configuration — **없음, Next.js 초기화 시 생성**

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming (Python)** | ECC rules 참조 | snake_case 함수/변수, PascalCase 클래스 | High |
| **Naming (TS)** | ECC rules 참조 | camelCase 함수/변수, PascalCase 컴포넌트 | High |
| **Folder structure** | 이번 Plan에서 정의 | 위 7.3 구조 따름 | High |
| **API 규약** | 미정 | RESTful, /api/v1/ 프리픽스, 일관된 응답 포맷 | High |
| **Git branch** | main만 존재 | main + feature/* + hotfix/* | Medium |
| **Error handling** | ECC rules 참조 | FastAPI HTTPException, 프론트 toast 알림 | Medium |
| **Import order** | 미정 | stdlib > third-party > local (isort) | Low |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `DATABASE_URL` | PostgreSQL 연결 문자열 | Server | V |
| `REDIS_URL` | Redis 연결 | Server | V |
| `JWT_SECRET_KEY` | JWT 서명 키 | Server | V |
| `JWT_ALGORITHM` | JWT 알고리즘 (HS256) | Server | V |
| `ANTHROPIC_API_KEY` | Claude API 키 | Server | V |
| `NEXT_PUBLIC_API_URL` | 백엔드 API 주소 | Client | V |
| `CVM_HOST` | Tencent CVM IP/도메인 | CI/CD (GitHub Secrets) | V |
| `CVM_SSH_KEY` | CVM SSH 접속 키 | CI/CD (GitHub Secrets) | V |

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 (Schema) | Pending | `docs/01-plan/schema.md` | `/bkit:phase-1-schema` |
| Phase 2 (Convention) | Pending | `docs/01-plan/conventions.md` | `/bkit:phase-2-convention` |

---

## 9. Implementation Strategy (Clean Architecture 반영)

**Design Phase 결정사항**: Option B (Clean Architecture) 채택 → Sprint 구성 재조정.
회계 자동화 완성 목표를 5월 중순으로 현실화하고, 4/21 미팅은 "설계+로그인 데모" 수준으로 조정.

### 9.1 Sprint 구성 (재조정)

#### Sprint 0: 아키텍처 골조 (4/16~4/18, 3일)

**목표**: Clean Architecture 4 레이어 뼈대 완성

| 작업 | 도구 | 산출물 |
|------|------|--------|
| 프로젝트 디렉터리 구조 생성 | Bash | backend/, frontend/, docker-compose.yml |
| Python 환경(uv/poetry) + FastAPI 스켈레톤 | ECC `python-reviewer` | backend/app/ 4 레이어 |
| Domain 레이어 스켈레톤 (Entity, Repo 인터페이스) | ECC `tdd-guide` | domain/entities/, repositories/ |
| SQLAlchemy 모델 + Alembic 초기 마이그레이션 | ECC `database-reviewer` | infrastructure/database/, alembic/ |
| Next.js + Tailwind + shadcn/ui 초기화 | ECC `typescript-reviewer` | frontend/src/, features/ |
| docker-compose.yml (postgres + redis + backend + frontend) | ECC `docker-patterns` | docker-compose.yml |

#### Sprint 1: 인증 + 기본 UI + CI/CD (4/19~4/25, 1주)

**목표**: 로그인 + 대시보드 쉘 + CVM 자동 배포. 4/21 미팅 데모 포함.

| 작업 | 도구 |
|------|------|
| Domain Unit Tests (User, PasswordHasher, JWTProvider) | ECC `tdd-guide` |
| Infrastructure 구현체 (SqlAlchemyUserRepository 등) | ECC `python-reviewer` |
| Application Use Cases (AuthenticateUser, RefreshToken) | ECC `python-reviewer` |
| Presentation: /api/v1/auth/* 라우터 | ECC `python-reviewer` |
| 시드 스크립트 (5개 부서 + 3명 테스트 사용자) | - |
| Frontend: 로그인 페이지 + 대시보드 쉘 + 라우팅 가드 | ECC `typescript-reviewer`, `frontend-patterns` |
| E2E Tests: 로그인→대시보드→로그아웃 | ECC `e2e-runner` |
| GitHub Actions → CVM 자동 배포 | ECC `github-ops` |
| **4/21 미팅 데모** | - |

#### Sprint 2: 백오피스 + 채팅 + 보안 (4/26~5/9, 2주)

**목표**: 뼈대 완전 완성. 2단계 회계 모듈 탑재 가능한 상태.

| 작업 | 도구 |
|------|------|
| Department, ChatMessage Domain + Infrastructure | ECC `python-reviewer`, `database-reviewer` |
| 사용자/부서 CRUD Use Cases + Routers | ECC `python-reviewer` |
| LLMProvider 추상화 + AnthropicLLMProvider 구현 | ECC `claude-api`, `backend-patterns` |
| 백오피스 UI (사용자/부서 관리) | ECC `frontend-patterns` |
| AI 채팅 UI (Haiku/Sonnet/Opus 모델 선택) | ECC `frontend-patterns` |
| Rate limiting (slowapi) + CORS + 보안 헤더 | ECC `security-reviewer` |
| HTTPS 적용 (Nginx + Let's Encrypt) | ECC `security-reviewer`, `docker-patterns` |
| 테스트 커버리지 80% 달성 | ECC `tdd-guide`, `e2e-runner` |
| 문서화 (README, API docs) | ECC `doc-updater` |

#### Sprint 3 (별도 PDCA): 회계 자동화 모듈 (5/10~5/중순)

1단계 뼈대 완성 후 별도 `/bkit:pdca plan accounting-automation`으로 시작.
Clean Architecture 덕분에 `features/accounting/`을 Domain+Application+Infrastructure+Presentation 레이어로 안전하게 추가 가능.

### 9.2 ECC + bkit 병행 전략 (실제 적용)

```
각 기능 개발 시:
1. /bkit:pdca design     ← 설계 문서 (bkit 주도)
2. /plan                 ← 구현 계획 (ECC planner)
3. /tdd                  ← 테스트 먼저 (ECC tdd-guide)
4. 코드 작성             ← ECC code-reviewer 자동 동작
5. /bkit:pdca analyze    ← 설계 vs 구현 갭 분석 (bkit)
```

---

## 10. DB Schema (Initial)

```sql
-- 부서
departments (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,  -- '마케팅1팀', '회계팀' 등
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
)

-- 사용자
users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'staff',  -- 'admin', 'manager', 'staff'
    department_id   INTEGER REFERENCES departments(id),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
)

-- AI 대화 이력
chat_history (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) NOT NULL,
    model           VARCHAR(50) NOT NULL,          -- 'haiku', 'sonnet', 'opus'
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    messages        JSONB NOT NULL,                -- 전체 대화 JSON
    created_at      TIMESTAMPTZ DEFAULT NOW()
)

-- API 사용량 집계 (월별)
api_usage_monthly (
    id              SERIAL PRIMARY KEY,
    department_id   INTEGER REFERENCES departments(id),
    year_month      VARCHAR(7) NOT NULL,           -- '2026-04'
    total_requests  INTEGER DEFAULT 0,
    total_input_tokens  BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,
    estimated_cost_usd  NUMERIC(10,4) DEFAULT 0,
    UNIQUE(department_id, year_month)
)
```

---

## 11. Next Steps

1. [ ] **즉시**: 이 Plan 문서 리뷰 및 확정
2. [ ] Design 문서 작성 (`/bkit:pdca design tk101-platform-foundation`)
3. [ ] Phase 1 Schema 정의 (`/bkit:phase-1-schema`)
4. [ ] Phase 2 Convention 정의 (`/bkit:phase-2-convention`)
5. [ ] Sprint 1 구현 착수 (`/bkit:pdca do tk101-platform-foundation`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-16 | Initial draft — 기존 5개 문서 기반 종합 | TK101 (junki7853) |
