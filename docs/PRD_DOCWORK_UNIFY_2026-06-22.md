# PRD — 문서 작업(Docwork) 통합: 문서생성 + 양식채우기

> **메타**
> - 작성일: 2026-06-22
> - 상태: 설계(draft) — 구현 전 합의용
> - 범위: `docgen`(새 문서 생성) + `form_filler`(양식 채우기) 통합, 출처 선택(RAG/업로드/둘다), 관리자 토큰 가시성
> - 관련 코드: `backend/app/routers/{docgen,forms}.py`, `backend/app/services/{docgen,form_filler}/`, `frontend/src/pages/forms/`, `frontend/src/config/modules.tsx`

---

## 1. 배경 / 문제 정의

문서 관련 모듈이 둘로 갈려 있고 인프라가 70% 겹친다.

- **docgen** — 주제 한 줄 → 제안서/계획서/보고서 **초안 생성**. stateless, NAS RAG만 참고, 토큰은 응답에 inline만.
- **form_filler** — 빈칸 있는 .docx **양식 채우기**. 잡(job) 영속화, 다종 출처(NAS+업로드), 토큰/비용 DB 저장, 감사이력까지 성숙.

문제:
1. 겹치는 부분(검색·LLM호출·출처강제·비용회계·검수·렌더)을 **두 군데서 따로 관리** → 드리프트(예: LLM-judge 검수는 docgen에만, 토큰 영속화는 form_filler에만).
2. docgen은 **사용자 업로드 문서 참고 불가**, 출처 선택 불가, 토큰 이력 없음.
3. UI가 분리돼 사용자에게 "뭘 써야 하지" 혼란.

## 2. 목표 / 비목표

**목표(In)**
- G1. 사용자에게 **"문서 작업"** 단일 진입점. 안에서 작업유형(새 문서 작성 / 양식 채우기) 선택.
- G2. 두 작업 모두 **출처 모드 선택**: `RAG만 | 업로드만 | 둘다`.
- G3. docgen에 **사용자 업로드 참고문서** 지원 + **잡 영속화**(비용/출처 기록).
- G4. **토큰/비용은 관리자만** 조회. 일반 사용자 화면엔 노출 안 함.
- G5. 겹치는 로직을 **공유 코어로 추출**해 한 번 고치면 양쪽 반영.
- G6. 산출물 품질 유지(6/22 배포한 theme/구조렌더) + 토큰 절약 레버 확보.

**비목표(Out)**
- 웹검색 출처(`web_search` enum은 존재하나 미사용) — 이번 범위 밖.
- 이미지/OCR 입력, 다국어 산출, 협업 동시편집.
- 검색 엔진 자체 변경(이미 Qdrant/Qwen3 단일소스, [PR#32] 완료).

## 3. 현황(As-Is) 비교

| 항목 | docgen | form_filler |
|---|---|---|
| 성격 | 생성형(빈 종이→구조) | 추출형(틀→슬롯 채움) |
| 잡 영속화 | ❌ stateless | ✅ `FormJob` 생명주기(enum status) |
| 출처 종류 | NAS RAG만(`use_nas` bool) | ✅ `FormDataSource.kind = nas_file/user_upload/user_input` |
| 사용자 업로드 | ❌ | ✅ `POST /jobs/{id}/sources/upload` |
| 출처 모드 선택 | 부분(use_nas on/off) | 부분(use_nas + 수동선택) |
| 토큰/비용 | 응답 inline `cost_usd` | ✅ DB `cost_usd,total_tokens_in/out,langfuse_trace_id` |
| 검수(LLM-judge) | ✅ `/review` | ❌ |
| 감사이력 | ❌ | ✅ `FormRevision` |
| 단일변수/섹션 재생성 | ✅ `/regenerate_section` | ✅ `/regenerate`(Haiku) |
| 산출물 | .docx/.pptx 스트림 | .docx 저장+다운로드 |

**핵심 인사이트**: 사용자가 원하는 "다종 출처 + 토큰 영속화"는 **form_filler에 이미 모델이 있다.** 통합은 곧 *form_filler의 잡/출처/비용 인프라를 공유 코어로 끌어올리고 docgen을 그 위로 올리는 것* + *docgen의 검수/구조렌더를 공유화해 form_filler도 쓰게 하는 것*이다.

## 4. 설계 원칙

1. **통합 surface, 분리 엔진** — 메뉴/UI/출처/비용/검수/렌더는 공유, 생성·채우기 *엔진*만 분리. (생성 vs 추출을 한 함수에 욱여넣지 않음)
2. **출처는 한 인터페이스 뒤로** — 엔진은 출처가 RAG인지 업로드인지 모른 채 `chunks[]`만 받는다.
3. **출처 강제 가드레일 재사용** — "sources에 없으면 null+출처표기"는 둘 다 공유.
4. **비용은 항상 잡에 적재** — 노출만 RBAC로 게이팅. (계산은 `llm_client.LLMResponse`가 이미 제공)
5. **DB 빅뱅 금지** — 단계적 마이그레이션, 각 단계는 독립 배포 가능.

## 5. To-Be 아키텍처

```
📁 문서 작업 (Documents)            ← 네비 1개, module gate 1개
├─ 작업유형: [새 문서 작성] / [양식 채우기]
│
├─ 🔧 공유 코어  app/services/documents/        (신설 — form_filler에서 추출)
│   ├─ sources/       출처 레이어: SourceMode(rag|uploaded|both) + collect()
│   ├─ llm_client     ← form_filler/llm_client.py 이동(네이밍 정상화)
│   ├─ nas_bridge     ← form_filler/nas_bridge.py 이동
│   ├─ extractor      업로드 추출/청크 ← form_filler/extractor.py 이동
│   ├─ cost           잡 비용/토큰 적재 헬퍼 + 관리자 집계
│   ├─ review         LLM-judge 검수 ← docgen에서 일반화
│   └─ render         theme/markdown_blocks(.pptx/.docx) ← docgen에서 일반화
│
├─ 🅐 생성 엔진  app/services/documents/generate/  (구조설계 프롬프트만 고유)
└─ 🅑 채우기 엔진 app/services/documents/fill/      (변수감지+슬롯매핑만 고유)
```

### 5.1 출처 레이어 (G2, G3)

```python
SourceMode = Literal["rag", "uploaded", "both"]

async def collect_sources(
    *, query: str, mode: SourceMode,
    uploaded: list[UploadedDoc], limit: int,
) -> list[SourceChunk]:
    # rag:      nas_bridge.search_relevant_chunks(query, limit)  → Qdrant
    # uploaded: 작으면 통째 주입 / 크면 추출→청크→(임베딩+검색)
    # both:     두 결과 머지 + dedup + 재랭크(reranker 재사용)
```
- `SourceChunk`는 출처 메타(kind, path/filename, score, excerpt) 보존 → 프롬프트 `[sources]`와 결과 출처표기에 그대로 사용.
- form_filler의 `FormDataSource.kind`(nas_file/user_upload/user_input)를 그대로 일반화.

### 5.2 토큰/비용 + 관리자 가시성 (G4)

- 모든 LLM 호출은 `LLMResponse{input_tokens, output_tokens, cache_*, cost_usd}` 반환(이미 존재).
- 잡 단위로 누적 적재(이미 `FormJob`이 함). docgen도 잡을 갖게 해 동일 적재.
- **노출**: 일반 사용자 응답/화면에서 cost 필드 제거. `GET /documents/admin/usage`(`require_admin`) 신설 — 기간/사용자/작업유형별 토큰·비용 집계. 프론트는 `ProtectedRoute`/role 체크로 관리자만 패널 표시.

### 5.3 토큰 절약 전략 (G6)

| 레버 | 효과 |
|---|---|
| 업로드 작을 때 검색 없이 통째 주입 + 캐싱 | 검색 0원, 정확도 100%, 입력 캐시할인 |
| 시스템 프롬프트 캐싱(이미 적용) | 반복호출 입력비 ~90%↓ |
| RAG `limit`/스코어 게이트 | 청크 수 = 입력 토큰 직접 통제 |
| 단일 재생성은 Haiku 라우팅(이미) | 부분수정 저비용 |
| both 모드 dedup | RAG·업로드 중복 청크 제거 |

## 6. 데이터 모델 변경

**원칙**: form_filler 테이블을 깨지 않고 docgen을 합류시킨다.

- **권장안 (단계적 일반화)**:
  - 1단계: `FormDataSource`/비용 컬럼은 그대로. docgen에 **경량 잡** 도입 — 옵션 A) `FormJob`을 `DocJob`으로 일반화하고 `kind = fill | generate` 컬럼 추가, 출처/매핑은 fill 전용. 옵션 B) 별도 `docgen_jobs` 테이블 + 공유 cost mixin.
  - **추천: 옵션 A(일반화)** — 비용/출처/이력 인프라를 한 테이블군에서 공유. 단 마이그레이션 비용 있음(컬럼 추가 + 기존 row backfill `kind='fill'`).
- 출처 모드 필드: 잡에 `source_mode` 추가.
- (열려있음 ➜ §11 Q2) docgen을 잡 기반으로 갈지 stateless 유지할지 — 추천은 잡 기반(업로드 첨부·관리자 토큰 이력 위해 필요).

## 7. API 변경(초안)

목표 네임스페이스 `/api/documents/*` (기존 `/api/docgen`,`/api/forms`는 당분간 alias 유지 → 프론트 점진 이전).

- 공유: `POST /documents/jobs`(kind, source_mode), `POST /documents/jobs/{id}/sources/upload`, `POST /documents/jobs/{id}/sources/nas`, `GET /documents/jobs/{id}`, `GET /documents/jobs/{id}/download`
- 생성: `POST /documents/jobs/{id}/generate`, `POST /documents/jobs/{id}/regenerate_section`, `POST /documents/jobs/{id}/review`, `POST /documents/jobs/{id}/render(_pptx)`
- 채우기: `POST /documents/templates/analyze`, `.../run_mapping`, `.../mappings/{key}`, `.../regenerate`
- 관리자: `GET /documents/admin/usage`(`require_admin`)

## 8. UI/UX (G1, G4)

- 네비 `modules.tsx`: 기존 3개(문서 자동 작성/문서 생성/양식 라이브러리)를 **"문서 작업"** 1개 그룹으로. 진입 후 작업유형 선택 카드.
- **출처 선택 컴포넌트(공유)**: 라디오 `RAG만 | 업로드만 | 둘다` + 업로드 드롭존 + (둘다일 때) 검색쿼리 입력. 생성·채우기 양쪽에서 재사용.
- 결과: 초안 미리보기 + 출처 배지 + 섹션/변수 재생성 버튼.
- **관리자 토큰 패널**: 일반 사용자엔 숨김. 관리자에게만 잡별/기간별 토큰·비용 + Langfuse 링크.
- 원칙: 유저 친화(작업유형·출처가 한눈에) + 결과 퀄리티(구조렌더·검수 기본 노출).

## 9. 롤아웃 — 단계별 PR

1. **PR-A 인프라 정상화(무동작변경)**: 앱 전역 인프라를 중립 위치로 이동 —
   `form_filler/llm_client.py → services/llm/client.py`, `form_filler/nas_bridge.py → services/nas_search/bridge.py`.
   전 importer(docgen·form_filler·distribution·translation·playground) 경로 갱신 + `services/documents/` 패키지 스켈레톤 생성. 순수 리팩토링 + 컨테이너 import 테스트.
2. **PR-B 출처 레이어 + docgen 업로드/잡화**: `SourceMode` collect(), docgen 잡 도입(옵션 A 마이그레이션), 업로드 첨부.
3. **PR-C 검수·렌더 공유화**: docgen의 LLM-judge/구조렌더를 공유로, form_filler도 사용.
4. **PR-D UI 통합**: "문서 작업" 네비 + 출처 선택 컴포넌트 + 작업유형 카드.
5. **PR-E 관리자 토큰 패널**: `/documents/admin/usage` + 프론트 패널 + 사용자 화면 cost 제거.

각 PR 독립 배포·롤백 가능. 기존 `/api/docgen`,`/api/forms` alias 유지하다 PR-D 이후 제거.

## 10. 리스크

- R1. 잡 일반화(옵션 A) 마이그레이션 — 기존 FormJob row backfill 필요. → 단계 분리 + 다운그레이드 경로.
- R2. UI 전면 개편 회귀 — 출처 컴포넌트 공유화 시 양 화면 동시 영향. → 컴포넌트 단위 비주얼 회귀 테스트.
- R3. both 모드 토큰 폭증 — dedup/limit 게이트 필수. 관리자 패널로 조기 감지.
- R4. alias 기간 중 이중 경로 유지비.

## 11. 결정 사항 / 미해결 질문

**확정(2026-06-22)**
- **Q1. 메뉴 명칭** = **"문서 작업"**.
- **Q2. docgen 잡 영속화** = **잡 기반으로 전환**(업로드첨부·관리자 토큰이력 위해).
- **Q3. 데이터 모델** = **FormJob 일반화**(`kind = fill | generate` 컬럼 추가, 기존 row `kind='fill'` backfill).

**미해결**
- **Q4. 양식채우기 "생성형 보강"**(빈 양식이지만 자료로 문장 생성) — 두 엔진 경계 흐려짐 주의. 추후 결정.

> **정정(인프라 위치)**: `llm_client`·`nas_bridge`는 docgen/form_filler뿐 아니라
> distribution·translation·playground 까지 쓰는 **앱 전역 인프라**다(현재 `form_filler/`
> 아래 있는 건 네이밍 스멜). 따라서 `documents/`로 옮기지 않고 중립 위치로 정상화한다:
> `llm_client → app/services/llm/client.py`(기존 중립 llm 패키지 합류),
> `nas_bridge → app/services/nas_search/bridge.py`(검색 인프라와 co-locate).
> `app/services/documents/`는 **docwork 전용 공유코드**(출처레이어·잡비용·검수·렌더)만 담는다(PR-B/C에서 신설).

## 12. 성공 기준

- 한 메뉴에서 생성·채우기 모두 수행, 출처 3모드 동작.
- docgen이 업로드 문서만/둘다 참고 가능, 결과 출처표기 정확.
- 토큰·비용이 잡에 적재되고 관리자만 조회.
- 공유 코어 1회 수정이 양 엔진에 반영(드리프트 해소).
- 산출물 품질(구조렌더+검수) 회귀 없음.
