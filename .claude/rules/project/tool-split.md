# bkit ↔ ECC 도구 분담 상세

> CLAUDE.md §3에서 참조. 도구 선택이 애매할 때 이 파일을 열어보세요.

## 기본 원칙

- **bkit = 프로세스 매니저** (무엇을/왜/어떻게 만들지 — PDCA 흐름 관리)
- **ECC = 기술 전문가** (어떻게 제대로 만들지 — 코드 품질/보안/테스트)
- **중첩 금지**: 같은 작업을 두 도구로 동시에 하지 말 것

## 상황별 1차/2차 도구 매트릭스

### 기획·설계 단계

| 상황 | 1차 도구 | 2차 도구 | 비고 |
|------|---------|---------|------|
| 새 기능 기획 시작 | `/bkit:pdca plan` | - | Checkpoint 1, 2 답변 |
| 데이터 모델 정의 | `/bkit:phase-1-schema` | ECC `database-reviewer` | 스키마 정합성 체크 |
| 코딩 컨벤션 정의 | `/bkit:phase-2-convention` | - | 프로젝트 1회만 |
| UI 목업 빠르게 | `/bkit:phase-3-mockup` | ECC `frontend-patterns` | 단순 백오피스는 스킵 가능 |
| 설계 문서 작성 | `/bkit:pdca design` | ECC `architect` (복잡 시) | Clean Arch는 기본 |
| 구현 계획 세부화 | ECC `/plan` 또는 `planner` | - | 파일별 작업 순서 |

### 구현 단계

| 상황 | 1차 도구 | 2차 도구 | 비고 |
|------|---------|---------|------|
| 테스트 먼저 작성 (TDD) | ECC `/tdd` / `tdd-guide` | - | L0 Domain부터 |
| FastAPI 코드 작성 | ECC `python-reviewer` (자동) | `backend-patterns` | Domain→Infra→App→Pres 순 |
| Next.js 코드 작성 | ECC `typescript-reviewer` (자동) | `frontend-patterns` | types→api→services→hooks→components |
| PostgreSQL 스키마/쿼리 | ECC `database-reviewer` | `postgres-patterns` | 인덱스 리뷰 필수 |
| Claude API 연동 | ECC `claude-api` skill | - | - |
| Docker 구성 | ECC `docker-patterns` | - | - |
| 구현 진행 추적 | `/bkit:pdca do` | - | `--scope <module>` 활용 |

### 보안·검증 단계

| 상황 | 1차 도구 | 2차 도구 | 비고 |
|------|---------|---------|------|
| 인증/보안 코드 | ECC `security-reviewer` (**필수**) | - | 커밋 전 반드시 |
| 빌드 에러 | ECC `build-error-resolver` | - | 근본 원인 추적 |
| QA 계획/실행 | `/bkit:qa-phase` | ECC `e2e-runner` | L1~L5 테스트 |
| 설계↔구현 갭 분석 | `/bkit:pdca analyze` | - | 90% 목표 |
| 회귀 개선 자동화 | `/bkit:pdca iterate` | - | 최대 5회 |

### 배포·운영 단계

| 상황 | 1차 도구 | 2차 도구 | 비고 |
|------|---------|---------|------|
| CI/CD 파이프라인 설정 | ECC `github-ops` | - | workflows/ 파일 |
| 배포 실행 | `/bkit:deploy` | ECC `github-ops` | 환경별 전략 |
| 완료 보고서 | `/bkit:pdca report` | - | PRD→Plan→Design→결과 종합 |
| 문서 아카이브 | `/bkit:pdca archive` | - | docs/archive/로 이동 |

## 중첩 금지 예시

| ❌ 하지 말 것 | ✅ 이렇게 |
|------|-----------|
| bkit와 ECC 둘 다로 같은 코드 리뷰 | ECC 언어별 reviewer만 |
| ECC TDD + bkit QA로 동시에 테스트 작성 | Do는 ECC tdd, 최종 검증만 bkit qa-phase |
| `/plan` 두 번 호출 | 1회만 — 추가 변경은 Plan 문서 직접 수정 |
| 같은 기능에 대해 ECC `architect` + `/bkit:pdca design` 병렬 | bkit가 주도, ECC는 설계가 복잡할 때 보조 호출 |

## 의사결정 플로우차트

```
질문: 지금 뭘 해야 하지?
│
├─ "무엇을 왜 만들지 정하고 싶다"
│   → bkit (pdca plan / phase-1-schema / phase-3-mockup)
│
├─ "코드를 실제로 작성하고 싶다"
│   → ECC (python-reviewer / typescript-reviewer 자동 + tdd-guide)
│
├─ "결과물을 검증하고 싶다"
│   → bkit (qa-phase) + ECC (e2e-runner, security-reviewer)
│
├─ "품질 갭을 분석하고 개선"
│   → bkit (pdca analyze / iterate)
│
└─ "배포하고 기록 정리"
    → bkit (deploy / report / archive)
```
