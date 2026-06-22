# CLAUDE.md — TK101 작업 지침

이 파일은 세션마다 자동 로드된다. **여기 적힌 방식대로 과정 질문 없이 바로 일한다.**

## 1. 기본 모드 = 완전 자율

요청(또는 `docs/BACKLOG.md`의 항목)을 받으면 **끝까지 스스로 굴린다**:

```
조사/설계 → 구현 → 검증 → 브랜치 커밋 → PR → 머지 → 배포 → 운영 검증 → 결과 보고
```

- **"이거 할까요?" 류의 과정 질문을 하지 않는다.** 합리적 기본값으로 진행하고, 판단한 가정은 한 줄로 명시한다(틀리면 오너가 교정).
- 독립적인 작업은 **병렬 멀티에이전트(워크트리 격리)** 로 동시에 돌리고, **통합·배포는 순차로**(단일 러너 레이스 회피).
- 완료 단위로만 보고한다. 중간 확인을 요구하지 않는다.
- 큰 작업은 단계(PR)로 쪼개 각각 배포·검증한다.

## 2. 멈춰서 먼저 물어봐야 하는 것 (오직 이 둘)

1. **되돌리기 어려운 운영 파괴 작업** — 운영 데이터/파일 삭제·DROP, 대량/비가역 마이그레이션, 운영 계정·콘텐츠 영구삭제.
2. **비용 크게 드는 작업** — 대량 LLM 호출·임베딩 등 토큰/요금이 크게 발생하는 것.

그 외 제품/UX/데이터모델 결정은 **물어보지 말고** 합리적 안으로 진행 + 가정 명시. 보안/인프라도 **코드·서버 설정은 자율**, 단 **콘솔·외부계정·비밀번호·방화벽 콘솔**이 필요한 단계만 오너에게 명확한 절차로 넘긴다.

> 파괴적 작업 판단은 `safety-guard` 스킬 기준을 따른다(운영 데이터/파일/마이그레이션 보호).

## 3. 검증 게이트 (이걸 통과해야 "완료")

배포 전: `py_compile` / `npx tsc --noEmit` + `npx vite build`(exit 0) / 컨테이너 `import app.main`.
DB 마이그레이션: **`tk101_dev`(dev 컨테이너)에서 적용·롤백·재적용 테스트 후** 운영 배포(운영 alembic은 배포 시 실행).
배포 후: **운영에서 실제 검증**(라우트 등록/실데이터/리비전). **운영 검증 없이 "완료"라고 하지 않는다.** 실패하면 그대로 보고.

## 4. 기술 컨벤션

- **항상 브랜치 → PR → 머지**(main 직접 push 금지). 머지가 곧 배포 트리거.
- 커밋 메시지: `<type>(<scope>): <subject>` (feat/fix/refactor/chore/docs…), 끝에 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- `frontend/vite.config.ts`의 dev 프록시 변경("커밋 안 함" 표식)은 **항상 커밋 제외**.
- **동적 설계 원칙**: 계정/브랜드/부서/플랫폼을 하드코딩하지 않는다(예: 서울시 고정 금지). 항상 DB/코퍼스를 순회 → 나중에 추가돼도 자동 반영.
- UI는 한국어. 스택: React 19 + antd v6 + recharts 2.x, FastAPI + SQLAlchemy(async) + alembic. openpyxl 사용 가능.

## 5. 운영 환경

- Tencent CVM 서울(43.155.202.112). 배포 = main 푸시 → self-hosted runner `docker compose up -d --build` + (컨테이너 내) `alembic upgrade head`.
- 컨테이너: tk101-backend(운영, 이미지 베이크), tk101-backend-dev(`/srv`에 작업트리 마운트 — import/마이그레이션 테스트용, DB=`tk101_dev`), tk101-postgres, tk101-qdrant, tk101-frontend(nginx).
- 검색 = Qdrant `docs_text`(Qwen3 2560d) 단일소스. 적재는 외부 파이프라인 `/home/ubuntu/tk101-rag`. 인앱 인덱서·pgvector는 제거됨.
- nginx `/api/` 타임아웃 300s. NAS: `/mnt/nas`(ro), `/mnt/nas-rw`(rw), `/mnt/nas-rnd`(rnd).
- gh 인증됨(tk101-ai). 배포 확인: `gh run watch`.

## 6. 백로그 운영

- 할 일은 `docs/BACKLOG.md`에 모은다(오너가 추가/수정). 세션 시작 시 거기서 **우선순위 높은 것부터 자율로 처리**한다.
- 처리 시작/완료를 백로그에 표시(`[ ]`→`[~]`→`[x]`)하고, 완료분은 PR번호와 함께 남긴다.
- "물어봐야 하는 둘(§2)"에 해당하는 항목은 백로그에 `⚠️오너승인`으로 표시하고 그 항목만 멈춰 확인.

## 7. 요청 라우팅 (요청 종류 → 쓸 도구)

말한 의도에 따라 아래 ECC 도구로 자동 라우팅한다. (큐레이션: `agent-sort` 결과 — DAILY만 사용, off-stack은 `rules-library/`로 분리됨)

| 네가 이렇게 말하면 | 흐름 |
|---|---|
| **"X 만들어줘 / 추가해줘"** | 기획·계획(`planner`/`architect`/`code-explorer`로 기존코드 파악) → **오너 승인(§1 게이트)** → 병렬 개발(워크트리, `claude-devfleet`/`team-builder`) → 다중 리뷰 → 통합·검증·배포 |
| **"코드 리뷰해줘"** | **멀티에이전트 병렬 리뷰**: `code-reviewer` + `python-reviewer` + `typescript-reviewer` + `security-reviewer` + `database-reviewer` + `silent-failure-hunter` → 종합 보고 (`/code-review`, `santa-method`). 항상 다중. |
| **"퀄리티/리팩토링/개선"** | `code-simplifier` + `refactor-cleaner` + `performance-optimizer` + `comment-analyzer` (`/quality-gate`·`/refactor-clean`·`/verify`) |
| **"테스트/검증"** | `tdd-guide` (pytest/vitest) + `/test-coverage`·`/e2e` |

활성 스킬·에이전트는 DAILY 세트(자세한 분류는 본 세션 agent-sort 결과). LIBRARY는 필요 시 Skill/Agent 도구로 온디맨드 호출(별도 라우터 없음).

## 8. 참고 문서
설계/이력은 `docs/`: `prd/`(PRD·SPEC·DESIGN), `reviews/`(보안/도메인/임베딩 검토), `worklogs/`(날짜별). 최신 작업이력: `docs/worklogs/`. 비활성 룰/스킬 큐레이션: off-stack 룰은 `.claude/rules-library/`.
