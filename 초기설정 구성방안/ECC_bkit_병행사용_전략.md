# ECC + bkit 병행 사용 전략

## 개요

TK101 사내 AI 자동화 플랫폼 구축에서 기존 ECC(Everything Claude Code)와 bkit 플러그인을 병행 사용하는 전략.

- **bkit**: 프로세스 매니저 (기획 → 설계 → QA → 배포 흐름 관리)
- **ECC**: 기술 전문가 (코드 품질/보안/성능 보장)
- **효과**: 1인 개발에서 PM + 시니어 엔지니어를 동시에 두는 구조

---

## 역할 분담 요약

| 역할 | bkit | ECC (기존) |
|------|------|------------|
| "무엇을 만들까" (기획/설계/프로세스) | **주도** | 보조 |
| "어떻게 만들까" (코드 품질/보안/테스트) | 보조 | **주도** |
| "잘 만들었나" (QA/리뷰) | 테스트 계획 | 코드 리뷰/보안 감사 |
| "어떻게 배포하나" (배포/운영) | 배포 관리 | CI/CD 설정 |

---

## 1단계 — 뼈대 구축 (서버/DB/인증/기본UI)

| 작업 | 사용 도구 | 이유 |
|------|-----------|------|
| 프로젝트 기획/PRD 작성 | `/bkit:pdca` + `/bkit:plan-plus` | PDCA 기반 체계적 기획, 브레인스토밍 |
| 데이터 모델 정의 (사용자, 부서, 권한) | `/bkit:phase-1-schema` | 엔티티/관계 정의 구조화 |
| 코딩 컨벤션 정의 | `/bkit:phase-2-convention` | Python/TS 규칙 문서화 |
| UI 목업 (로그인, 대시보드) | `/bkit:phase-3-mockup` | HTML/CSS 프로토타입 빠르게 |
| FastAPI 백엔드 코드 작성 | ECC `python-reviewer` + `backend-patterns` | 언어별 전문 리뷰 |
| Next.js 프론트 코드 작성 | ECC `typescript-reviewer` + `frontend-patterns` | 프론트 코드 품질 |
| PostgreSQL 스키마 설계 | ECC `database-reviewer` + `postgres-patterns` | 쿼리/인덱스 최적화 |
| 인증/RBAC 구현 | ECC `security-reviewer` | 보안 취약점 감지 필수 |
| Docker Compose 구성 | ECC `docker-patterns` | 컨테이너화 패턴 |
| CI/CD 파이프라인 | ECC `github-ops` → `/bkit:deploy` | 설정은 ECC, 배포 관리는 bkit |
| 코드 리뷰 | ECC `code-reviewer` + `python-reviewer` | 매 커밋 자동 리뷰 |
| 진행 상황 추적 | `/bkit:pdca` | PDCA 사이클로 진척 관리 |

---

## 2단계 — 회계 자동화 모듈

| 작업 | 사용 도구 | 이유 |
|------|-----------|------|
| 회계 모듈 PRD | `/bkit:pdca` + `/bkit:pm-discovery` | PM 에이전트로 요구사항 구체화 |
| 은행 파싱 로직 구현 | ECC `python-reviewer` + `tdd-guide` | TDD로 파서 정확도 보장 |
| 세금계산서 매칭 로직 | ECC `tdd-guide` | 테스트 먼저 → 정확한 매칭 |
| 엑셀 리포트 생성 | ECC `python-patterns` | openpyxl/pandas 패턴 |
| 대시보드 UI | `/bkit:phase-6-ui-integration` + ECC `frontend-patterns` | UI 연동 + 프론트 품질 |
| QA/테스트 | `/bkit:qa-phase` + ECC `e2e-runner` | bkit L1-L5 테스트 계획 + ECC E2E 실행 |
| 보안 점검 | ECC `security-reviewer` | 회계 데이터 = 민감 데이터 |

---

## 3단계 — 확장 (카카오톡, 멀티AI, NAS)

| 작업 | 사용 도구 |
|------|-----------|
| 카카오톡 API 연동 | ECC `api-connector-builder` + `security-reviewer` |
| 멀티 AI 추상화 레이어 | ECC `architect` + `planner` |
| 에이전트 병렬 처리 | ECC `agentic-engineering` + `enterprise-agent-ops` |
| 전체 파이프라인 관리 | `/bkit:development-pipeline` (9단계) |

---

## 실제 워크플로우 (기능 하나 개발 시)

```
1. /bkit:pdca plan        ← 기능 기획 (PDCA Plan)
2. /bkit:phase-1-schema   ← 데이터 모델 정의
3. /bkit:phase-3-mockup   ← UI 프로토타입
4. /plan                  ← ECC planner로 구현 계획
5. /tdd                   ← ECC TDD 가이드로 테스트 먼저
6. 코드 작성              ← ECC 자동 code-reviewer 동작
7. /bkit:qa-phase         ← QA 테스트 계획/실행
8. /bkit:pdca analyze     ← 결과 분석/회고
9. /bkit:deploy           ← 배포
```

---

## bkit 주요 스킬 목록

### 핵심/도움말
| 스킬 | 설명 |
|------|------|
| `/bkit` | 플러그인 도움말, 사용 가능한 기능 목록 |
| `/bkit:bkit-rules` | PDCA 방법론, 레벨 감지, 품질 표준 등 핵심 규칙 |
| `/bkit:skill-status` | 로드된 스킬 인벤토리 |
| `/bkit:skill-create` | 프로젝트 로컬 스킬 대화형 생성 |
| `/bkit:output-style-setup` | bkit 출력 스타일 설치 |

### bkend.ai 백엔드 (BaaS)
| 스킬 | 설명 |
|------|------|
| `/bkit:bkend-quickstart` | 온보딩 — MCP 설정, 테넌트/유저 모델, 첫 프로젝트 |
| `/bkit:bkend-auth` | 인증 — 이메일/소셜 로그인, JWT, RBAC, 세션 관리 |
| `/bkit:bkend-data` | 데이터베이스 — CRUD, 컬럼 타입, 필터링, 정렬, 관계 |
| `/bkit:bkend-storage` | 파일 스토리지 — 업로드, 다운로드, 버킷 |
| `/bkit:bkend-cookbook` | 프로젝트 튜토리얼 및 에러 트러블슈팅 |

### PDCA 사이클 관리
| 스킬 | 설명 |
|------|------|
| `/bkit:pdca` | 통합 PDCA 사이클 — plan, design, do, analyze, iterate, report |
| `/bkit:pdca-batch` | 다중 PDCA 기능 및 배치 작업 관리 |
| `/bkit:plan-plus` | 브레인스토밍 강화 PDCA 기획 |
| `/bkit:rollback` | PDCA 체크포인트 및 롤백 |

### 개발 파이프라인
| 스킬 | 설명 |
|------|------|
| `/bkit:development-pipeline` | 9단계 개발 파이프라인 가이드 |
| `/bkit:phase-1-schema` | 1단계: 용어, 데이터 구조, 엔티티, 관계 정의 |
| `/bkit:phase-2-convention` | 2단계: 코딩 규칙, 컨벤션, 표준 정의 |
| `/bkit:phase-3-mockup` | 3단계: UI/UX 목업 및 프로토타입 |
| `/bkit:phase-6-ui-integration` | 6단계: 프론트엔드 UI 구현 및 백엔드 API 연동 |
| `/bkit:phase-8-review` | 8단계: 코드베이스 품질 검증 |
| `/bkit:qa-phase` | QA 단계 — L1-L5 테스트 계획, 생성, 실행, 리포트 |

### 개발 도구
| 스킬 | 설명 |
|------|------|
| `/bkit:code-review` | 코드 리뷰 — 품질 분석, 버그 감지 |
| `/bkit:deploy` | 배포 — dev/staging/prod 환경별 전략 |
| `/bkit:control` | 자동화 레벨(L0-L4) 제어, 가드레일 관리 |
| `/bkit:audit` | 감사 로그, 의사결정 추적 |

### 앱 개발 가이드
| 스킬 | 설명 |
|------|------|
| `/bkit:dynamic` | 풀스택 개발 (bkend.ai BaaS 연동) |
| `/bkit:starter` | 정적 웹 개발 — HTML/CSS/JS, Next.js App Router |
| `/bkit:mobile-app` | 모바일 앱 — React Native, Flutter, Expo |
| `/bkit:desktop-app` | 데스크톱 앱 — Electron, Tauri |
| `/bkit:enterprise` | 엔터프라이즈 — 마이크로서비스, Kubernetes, Terraform |

### 기타
| 스킬 | 설명 |
|------|------|
| `/bkit:bkit-templates` | PDCA 문서 템플릿 |
| `/bkit:claude-code-learning` | Claude Code 설정/최적화 학습 |
| `/bkit:pm-discovery` | PM 에이전트 팀 — 자동 제품 발견, 전략, PRD 생성 |
| `/bkit:zero-script-qa` | 스크립트 없는 QA — JSON 로깅 + Docker 모니터링 |
| `/bkit:btw` | 작업 중 개선 제안 수집/관리 |

---

## ECC 주요 에이전트/스킬 (프로젝트에서 사용할 것)

### 에이전트
| 에이전트 | 용도 |
|---------|------|
| `python-reviewer` | FastAPI 백엔드 코드 리뷰 |
| `typescript-reviewer` | Next.js 프론트엔드 코드 리뷰 |
| `database-reviewer` | PostgreSQL 스키마/쿼리 리뷰 |
| `security-reviewer` | 보안 취약점 감지 |
| `architect` | 시스템 설계 |
| `planner` | 기능 구현 계획 |
| `code-reviewer` | 일반 코드 리뷰 |
| `tdd-guide` | 테스트 주도 개발 |
| `build-error-resolver` | 빌드 에러 해결 |
| `e2e-runner` | E2E 테스트 |

### 스킬
| 스킬 | 용도 |
|------|------|
| `python-patterns` | Python 코딩 패턴 |
| `claude-api` | Claude API 연동 |
| `postgres-patterns` | DB 설계/최적화 |
| `frontend-patterns` | React 컴포넌트 패턴 |
| `backend-patterns` | 백엔드 아키텍처 |
| `docker-patterns` | Docker 컨테이너화 |
| `github-ops` | GitHub Actions CI/CD |
| `api-design` | REST API 설계 |
| `agentic-engineering` | 에이전트 병렬 실행 |
| `security-review` | 보안 감사 |

---

## 기능 비교 매트릭스

| 기능 | ECC | bkit | 우위 |
|------|:---:|:---:|:---:|
| 코드 리뷰 | 47개 언어별 전문 에이전트 | 범용 1개 | **ECC** |
| TDD/테스팅 | 언어별 TDD 가이드 + E2E | QA 단계 (L1-L5) | **ECC** |
| 보안 분석 | 전용 security-reviewer + 규칙 | 없음 | **ECC** |
| 빌드 에러 해결 | 언어별 build-resolver 7개 | 없음 | **ECC** |
| 프로젝트 기획 | planner + architect | PDCA + PM 에이전트 | **bkit** |
| 개발 파이프라인 | 자유 형식 | 9단계 구조화 | **bkit** |
| BaaS 연동 | 없음 | bkend.ai 풀스택 | **bkit** |
| 자동화 레벨 제어 | 없음 | L0-L4 가드레일 | **bkit** |
| 감사/추적 | 없음 | audit 로그, 의사결정 추적 | **bkit** |
| 문서 템플릿 | docs 스킬 | PDCA 템플릿 | **bkit** |

---

## 작성일: 2026-04-16
