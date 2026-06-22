# 구현 스펙 — Docwork #2(재생성/검수 업로드 반영) + #1(관리자 토큰 가시성 + 잡 영속화)

> **메타**: 2026-06-22 · 설계 스펙(구현 전 합의용) · 관련 [PRD](PRD_DOCWORK_UNIFY_2026-06-22.md)
> 현재 상태 기준 사실: 생성기(`generate_document/regenerate_section/review_document`)는 이미 `chunks: list[NasChunkHit]`를 받음 → **생성기 변경 0**. `collect_sources()`(documents/sources.py)가 단일 seam. alembic head=**032** → 다음 **033**.

---

## FEATURE #2 — 재생성/검수에 업로드 자료 반영

### 권고: 접근(a) 무상태 멀티파트 재전송
근거: 생성기는 이미 source-shaped. 프론트가 `fileList`를 세션 내내 state로 보유 → 재전송 비용 무. 잡 영속화(접근 b)와 디커플 → 빠른 일관성 윈을 마이그레이션과 분리. 업로드 재추출은 CPU만(임베딩·토큰 비용 0, score=1.0).
- 한계: 매 호출마다 업로드 재추출(파일 5×20MB 캡 내라 OK). 대용량 다수면 추후 (b).

### 백엔드 (`routers/docgen.py`)
- 공유 헬퍼 `_read_uploads(source_mode, files)` 추출(generate의 업로드 루프 DRY화).
- `/regenerate_section`·`/review`를 JSON→멀티파트(Form+File)로, `source_mode`+`files` 수용. 기존 `use_nas`/`nas_bridge.search` 분기 제거 → `collect_sources(query=..., mode=source_mode, uploaded=uploaded, limit=...)`.
- `/review`의 `sections`는 멀티파트로 객체배열 못 실음 → `sections_json`(JSON 문자열) 필드로 받아 `TypeAdapter(list[DocSection]).validate_json()` 파싱, 실패 시 422.
- 스키마: `DocSectionRegenRequest`/`DocReviewRequest`는 라우트에서 미사용 → 삭제 권장(grep로 타 참조 확인).

### 프론트
- `api/docgen.ts`: `regenerateSection`·`reviewDocument`를 FormData로. `use_nas` 제거→`source_mode`+`files`. review는 `sections_json: JSON.stringify(sections)`.
- `DocGenPage.tsx`: `files` 파생을 컴포넌트 상단으로 끌어올려 3개 핸들러 공유. `useNas` 파생/주석 제거. `handleRegenerate`·`regenerateFromReview`·`handleReview`에서 `use_nas:useNas`→`source_mode:sourceMode, files`.
- 백·프론트 동시 배포(요청 형태 변경). `api` 클라이언트는 FormData에 JSON 강제 안 함(=generate에서 이미 검증됨).

---

## FEATURE #1 — 관리자 전용 토큰/비용 + 잡 영속화

### Step 1 — 마이그레이션 033 (`form_jobs` 일반화)
- `kind` 컬럼: PG ENUM `form_job_kind('fill','generate')`, NOT NULL, `server_default='fill'` → 기존 row는 ADD COLUMN 시점에 원자적 backfill(별도 UPDATE 불필요). 기존 `forms.py create_job`(kind 미설정) 호환 위해 default 유지.
- `source_mode` 컬럼: `TEXT NULL`(rag/uploaded/both; fill 잡은 null). 두 번째 enum 회피 위해 TEXT.
- **상태(status)**: docgen은 다단계 없음 → **enum 값 추가 금지**(R-ENUM). generate 잡은 성공 시 `status='completed'`로 바로 생성(동기 단일호출). 실패는 미영속 or `failed`. `005_form_filler.py`의 `ENUM(..., create_type=False)` + `.create(checkfirst=True)` 관용구 사용.
- 인덱스: `ix_form_jobs_kind`, `(kind, created_at DESC)`(관리자 집계용).
- 모델(`models/form_filler.py`): `kind`/`source_mode` 매핑 추가. `template_id` 이미 nullable → generate 잡은 `template_id=None` 유효.

### Step 2 — `/generate`에서 잡 영속화
- **선결 gap(R-TOKENS)**: `generate_document`이 현재 토큰수/trace_id를 버림(cost_usd·model만 반환). `GeneratedDoc`에 `input_tokens/output_tokens/trace_id` 추가(가산적, 기존 필드 불변)하고 `resp`에서 채움.
- `generate`에 `db: AsyncSession = Depends(get_db)` 주입. 성공 후 `FormJob(kind='generate', source_mode=..., status='completed', cost_usd, total_tokens_in/out, langfuse_trace_id, user_id, completed_at)` insert. **try/except로 감싸 영속화 실패가 생성 응답을 막지 않게**(문서가 본 product, 회계는 best-effort).
- v1은 `/generate`만 영속화. 재생성/검수 토큰은 Langfuse엔 있으나 집계 미반영(접근 b 후속).

### Step 3 — 관리자 엔드포인트 `GET /api/documents/admin/usage`
- 신규 라우터 `routers/documents_admin.py`, `dependencies=[Depends(require_admin)]`(403). `main.py`에 include.
- 쿼리 파라미터: `start/end`(기본 최근 30일), `group_by(day|user|kind)`, `kind(fill|generate|all)`.
- 응답: `UsageResponse{group_by,start,end,rows[UsageRow{bucket,kind,job_count,tokens_in,tokens_out,cost_usd}],totals}`.
- `form_jobs` 단일 테이블에서 `func.sum/count` + GROUP BY. `(kind,created_at)` 인덱스가 backing. fill·generate 한 테이블 집계 = 일반화의 핵심 이득.

### Step 4 — RBAC + 패널 + 일반사용자 비용 숨김
- **4a 백엔드 비용 숨김**: `schemas/docgen.py`의 `DocGenResponse`/`DocSectionRegenResponse`/`DocReviewResponse`에서 `cost_usd` 제거. 라우터에서 해당 인자 제거(비용은 계산·영속화되지만 클라 미반환).
- **4b 프론트 비용 숨김**: `DocGenPage.tsx` 3개 성공 토스트에서 `$${cost}` 제거. `api/docgen.ts` 인터페이스 동기화.
- **4c 패널 게이팅**: 이 레포는 **모듈 기반**(`ProtectedRoute module="..."`, admin은 전 모듈 보유)이 관례. 권장: 모듈키 `documents_admin_usage` 신설 → `App.tsx`에 라우트 추가, 백엔드는 `require_admin`이 진짜 권위. 대안: `ProtectedRoute`에 `requireAdmin?` prop. 신규 페이지 `pages/documents/DocumentsUsagePage.tsx` + `api/documentsAdmin.ts`. 네비는 playground-admin 항목과 동일 방식.

---

## 안전 시퀀싱
1. **PR-#2**(Feature #2, 무상태 멀티파트) — 독립, 먼저.
2. **033 마이그레이션 + 모델** — `form_jobs.kind/source_mode` 읽기/쓰기 전에 `alembic upgrade head` 선행.
3. **생성기 토큰 노출 + `/generate` 영속화** — 033 + `GeneratedDoc` 가산 변경 의존(같은 PR 가능).
4. **관리자 엔드포인트** — 033 의존, Step2 데이터 활용(병행/후행 가능).
5. **비용숨김 + 패널** — 4a/4b는 Step2(영속화) 이후에(비용 보존 후 숨김). 패널은 Step3 의존.

권장 PR 묶음: **PR-#2** → **PR-E-1**(033+모델+생성기토큰+/generate 영속화) → **PR-E-2**(관리자 엔드포인트+패널+비용숨김).

## 리스크
- **R-ENUM(high)**: 기존 `form_job_status` enum에 값 추가는 alembic 지뢰(`ALTER TYPE ADD VALUE` 트랜잭션 제약·비가역). → 본 스펙은 회피(generate는 completed/failed만, kind는 신규 enum을 005식 관용구로 생성).
- **R1 backfill(low)**: `server_default='fill'`로 원자적, UPDATE 불필요. downgrade는 컬럼→enum 순 drop.
- **R-TOKENS(medium)**: 생성기 토큰 미노출 시 `total_tokens_in/out`이 0으로 영속 → 집계 과소. `GeneratedDoc` 변경을 Step2 하드 선결로.
- **영속화가 생성 막으면 안 됨(medium)**: db.add/commit을 try/except+log.
- **재생성/검수 토큰 미집계(알려진 한계)**: 접근(a)는 job_id 미전달 → /generate만 집계. v1 허용, 접근(b) 후속.
- **비용숨김 순서(low)**: 응답에서 cost 제거는 영속화(Step2) 이후에.

## 변경 파일
백엔드: `routers/docgen.py`, `schemas/docgen.py`, `services/docgen/generator.py`, `models/form_filler.py`, `alembic/versions/033_*.py`(신규), `routers/documents_admin.py`(신규), `schemas/documents_admin.py`(신규), `main.py`(include).
프론트: `api/docgen.ts`, `pages/forms/DocGenPage.tsx`, `App.tsx`, `config/modules.tsx`, `pages/documents/DocumentsUsagePage.tsx`(신규), `api/documentsAdmin.ts`(신규), (대안 선택 시)`components/ProtectedRoute.tsx`.
