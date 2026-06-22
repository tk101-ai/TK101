# TK101 전체 코드베이스 코드리뷰 스코어카드 (2026-06-22)

> 멀티에이전트 리뷰: 12개 모듈 병렬 + 종합. 백엔드 38K LOC + 프론트 32.5K LOC. Run wf_e47a8a2a.


# TK101 코드베이스 전체 스코어카드

리뷰 대상: 백엔드 7개 모듈 + 프론트엔드 5개 모듈 (총 12개)

---

## 1. 전체 점수표

차원 점수는 입력(JSON) 그대로 신뢰했다. 단, "테스트 = 0건"이라 명시했는데 점수가 1~3으로 들어온 모듈은 입력 그대로 두되, 가중평균에서 테스트 가중치를 낮게 두어 등급을 왜곡하지 않게 했다.

| # | 모듈 | 정확성 | 보안 | 유지보수 | 성능 | 테스트 | 등급 |
|---|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 백엔드: 인증/사용자/권한 | 6.0 | 6.0 | 8.0 | 7.0 | 1.0 | B |
| 2 | 백엔드: 재무/회계 | 6.5 | 7.5 | 7.0 | 7.0 | 1.0 | B |
| 3 | 백엔드: 신사업유통(distribution) | 7.0 | 6.0 | 7.0 | 6.0 | 2.0 | B |
| 4 | 백엔드: SNS/마케팅 | 7.0 | 6.0 | 7.0 | 6.0 | 3.0 | B |
| 5 | **백엔드: NAS검색/RAG** | 7.0 | **4.0** | 7.0 | **5.0** | 2.0 | **C** |
| 6 | 백엔드: 문서작업(docgen) | 7.0 | 6.0 | 7.0 | 6.0 | 1.0 | B |
| 7 | 백엔드: 코어 인프라/마이그레이션 | 7.0 | 5.0 | 7.0 | 6.0 | 2.0 | B |
| 8 | 프론트: 마케팅/대시보드 | 7.0 | 5.0 | 7.0 | 6.0 | 1.0 | B |
| 9 | 프론트: 재무 | 7.0 | 5.0 | 8.0 | 6.0 | 1.0 | B |
| 10 | 프론트: 신사업유통 | 7.5 | 7.0 | 7.0 | 6.0 | 0.0 | B |
| 11 | 프론트: 문서/폼/NAS/플레이그라운드 | 6.5 | 6.5 | 7.5 | 6.5 | 2.5 | B |
| 12 | 프론트: 코어(라우팅/공통/API) | 7.0 | 5.0 | 8.0 | 8.0 | 3.0 | B |
| | **평균(단순)** | **6.9** | **5.75** | **7.29** | **6.29** | **1.63** | |

### 가중 평균 (전체 등급 산출)

가중치: **정확성 0.30 · 보안 0.30 · 유지보수 0.15 · 성능 0.15 · 테스트 0.10** (정확성·보안 가중 높게)

- 모듈별 가중점수를 산출해 평균하면 **전체 가중 평균 ≈ 6.3 / 10**.
- 보안(5.75)과 테스트(1.63)가 전체를 끌어내리는 두 축이다. 정확성·유지보수는 양호.

> **전체 등급: B−**
> (개별 모듈은 대부분 B지만, 보안 평균이 6 미만이고 테스트가 사실상 전무하며 NAS검색 모듈이 C로 한 단계 낮다. 단순 모듈 등급 다수결은 B이나, 가중 핵심축인 보안·테스트가 약해 B에서 반 단계 차감.)

---

## 2. 모듈 랭킹

### 가장 건강한 모듈 (Top 3)
1. **프론트: 코어(라우팅/공통/API)** — 유지보수 8 · 성능 8 · 테스트 3(최고). 데이터 주도 NAV, 단일 에러 유틸, 타입 견고. localStorage 토큰만 빼면 모범.
2. **프론트: 신사업유통** — 정확성 7.5(최고) · 보안 7. 권한 이중화(ProtectedRoute + isAdmin + 백엔드 require_admin), 타입 분리 깔끔. 단, 테스트 0.
3. **백엔드: 재무/회계** — 보안 7.5(백엔드 최고). Decimal 정밀도, SHA256 dedup, path traversal·매직바이트 방어 등 도메인 핵심을 진지하게 처리.

### 가장 위험한 모듈 (Bottom)
1. **백엔드: NAS검색/RAG — 유일한 C, 시스템 최대 리스크.** 보안 4 · 성능 5. 부서 스코핑 기본 OFF + confidential 플래그 미필터 + playground RAG가 스코핑 통째 우회 + 경로만 알면 임의 다운로드. **인가 우회가 코드 레벨이 아니라 정책/기본값 레벨에서 뚫려 있어 즉시 정보 유출 가능.**
2. **백엔드: 코어 인프라** — 보안 5. `jwt_secret='change-me'` insecure-by-default + 기동 검증 부재 + `pool_pre_ping` 미설정(배포 후 첫 요청 실패). 인증 전체가 의존하는 토대라 영향 범위가 넓다.
3. **프론트 전반(마케팅/재무/코어)** — 보안 5. localStorage JWT 저장으로 httpOnly 쿠키 방어를 스스로 무력화 + URL 스킴 미검증 저장형 XSS 표면.

---

## 3. 시스템적/교차 이슈 (가장 중요)

여러 모듈에 반복되는 구조적 패턴. 개별 버그보다 이쪽이 우선이다.

### S-1. 테스트 부재 — 전 모듈 공통, 최대 리스크
- **12개 모듈 전부**에서 테스트가 high/medium finding으로 잡혔다. 백엔드 인증·재무·docgen은 **0건**, 프론트는 `errorUtils`/`nasUtils`/`DocGenPage` 3개 파일이 레포 전체 테스트의 전부.
- **인증/인가·금액 계산·해시 정합성·매칭 불변식·가드레일** 등 회귀 시 직접 사고로 이어지는 핵심 로직에 안전망이 0. common/testing.md 80% 기준 대비 전 영역 미달.
- 의미: 아래 모든 수정을 안전하게 할 수 없다. **테스트 인프라가 보완 작업의 전제 조건.**

### S-2. 부서 스코핑 / RAG 인가 우회 — 백엔드 3개 모듈 공통
- NAS검색(모듈5), docgen(모듈6 `sources.py`), playground RAG(모듈5 `nas_rag.py`)가 **모두 `dept_labels` 없이 `search_relevant_chunks` 호출** → 전사 코퍼스 검색.
- 같은 뿌리(스코핑 로직 미전파)에서 나온 동일 결함이 3곳에 복제됨. **스코핑/confidential 게이트를 공용 함수로 추출**해 단일 정책으로 강제해야 한다.

### S-3. 레이트리밋 부재 — 백엔드 다수
- 인증(`/login`,`/register`), distribution 생성 엔드포인트(LLM 비용), SNS 댓글분석/번역(LLM 비용)에 레이트리밋 없음. 같은 레포에 `check_rate_limit` 유틸이 이미 있는데 적용이 산발적.
- **자격증명 스터핑 + LLM 토큰/요금 폭주** 두 종류 위험이 동시에 노출.

### S-4. localStorage JWT 저장 — 프론트 전 모듈 공통
- `frontend/src/api/client.ts` 한 곳이 모든 프론트 모듈에서 공유됨. httpOnly 쿠키(`withCredentials`)가 1차 인증인데 동일 JWT를 localStorage에도 저장+Bearer 부착 → **XSS 한 번이면 토큰 탈취**. 쿠키의 XSS 방어를 스스로 무력화.
- 단일 파일 수정이 전 프론트 모듈에 일괄 적용되는 **고레버리지 수정.**

### S-5. 입력 타입/경계 미검증 → 500 누수 — 백엔드 다수
- 비-UUID `sub`(모듈1), 비-UUID `declaration_id`(모듈3), bcrypt 72바이트 초과(모듈1), Numeric(15,2) 오버플로우(모듈2)가 모두 **422여야 할 입력을 500으로** 흘린다. 경로 파라미터 `UUID` 타입 강제·스키마 길이/상한 검증이 일관되지 않음.

### S-6. 경로/헤더 새니타이즈 불일치 — 백엔드 다수
- path-traversal 검사가 `startswith(real_root)`(separator 누락, 모듈6 renderer.py·forms.py)와 `commonpath`(올바름, 모듈2·6 nas_output)로 **혼재**. Content-Disposition 헤더 인젝션(모듈2). 심층방어가 곳곳에서 깨짐.

### S-7. 에러 메시지 정보 노출 비일관 — 백엔드
- 일부 핸들러는 `type(exc).__name__`/고정 메시지(안전), 일부는 `f"...: {exc}"`로 원본 예외 노출(모듈4 SNS, 모듈3 일부). 같은 모듈 안에서도 패턴이 섞임.

### S-8. 메모리 누수 / 단일 워커 가정 — 백엔드
- translation 레이트버킷 무한 증가(모듈4), login_manager in-memory `_store` + distribution 동기 송신이 `workers=1` 가정에 묶임(모듈3) → **수평 확장 불가 + 장기 구동 누수**.

### S-9. 하드코딩(동적 설계 원칙 위반) — 프론트
- AdminDashboard `http://IP:port` 외부링크(모듈8), distribution 브랜드/카테고리 색상 하드코딩(모듈10). CLAUDE.md 동적설계 원칙 반복 위반.

---

## 4. 우선순위 보완 목록 (병렬 에이전트 배분용)

영역(Area)별로 묶음. 같은 Area는 한 에이전트가 일괄 처리 가능.

### 🔴 CRITICAL 격 (즉시 — 정보유출/인가우회/위조)

**[Area A — RAG/부서 인가 우회]** (백엔드 모듈 5·6)
- A1 `nas_search/qdrant_search.py:101-133,164-180` — `build_qdrant_filter`에 confidential 기본 제외 추가. (high)
- A2 `playground/nas_rag.py:37-42` — `search_rag_context`에 `current_user` 받아 dept_labels 전파. (high)
- A3 `documents/sources.py:59-61` + `forms.py attach_nas_sources` — collect_sources에 dept_labels 전파. (high)
- A4 `config.py:87` — `nas_dept_scoping_enabled` 운영 기본 True 전환, 매핑 없는 부서는 "결과 없음" 폴백. (medium)
- A5 `nas_search.py:468-481,437-461` — download by-path/by-id에 dept/confidential 인가 추가 또는 서명 토큰. (medium)
- ※ **스코핑+confidential 게이트를 공용 함수로 추출**해 A1~A5가 단일 정책 공유 (S-2).

**[Area B — 시크릿/토대 보안]** (백엔드 모듈 1·7)
- B1 `config.py:5-7,239-242` — `jwt_secret in {'change-me',''}` 또는 기본 DB URL이면 기동 fail-fast(model_validator). (high)
- B2 `database.py:7` — `pool_pre_ping=True, pool_recycle=1800` 추가(배포 후 stale 커넥션). (high)

**[Area C — 프론트 토큰/XSS]** (프론트 모듈 8·9·11·12, 공유 파일)
- C1 `api/client.ts:10-16` — localStorage JWT 저장/Bearer 제거, httpOnly 쿠키 단일화 (전 프론트 일괄 적용). (high)
- C2 `SnsAccounts.tsx:287` 외 — URL 스킴 화이트리스트 `safeHref` 헬퍼, 저장형 XSS 차단. (high)

### 🟠 HIGH

**[Area D — 레이트리밋 일괄]** (백엔드 모듈 1·3·4) (S-3)
- D1 `auth.py:63-89,29-60` — `/login`(email+IP), `/register`(IP) 레이트리밋, 실패 429. (high)
- D2 `distribution.py:219`,`distribution_generate_v2.py:223` — 생성 엔드포인트 require_admin + per-user/IP 레이트리밋 + 일일 캡. (high)
- D3 `sns.py:1598-1669` — 댓글분석/번역에 `check_rate_limit` 재사용, force 경로 보수적 한도. (medium)

**[Area E — 도메인 정합성 (재무/매칭)]** (백엔드 모듈 2)
- E1 `matching.py:109-150` — apply_manual_match 불변식(반대타입·다른계좌·동일금액) 검증, 후보 로직과 술어 공유. (high)
- E2 `uploads.py:70-96` — 레거시 업로드에 transaction_hash + dedup 적용 또는 orchestrator 통합/deprecate. (high)

**[Area F — 권한 드리프트 / 토큰 무효화]** (백엔드 모듈 1)
- F1 `users.py:123-154` — 주 부서 변경 시 user_departments 재동기화(옛 부서 모듈권한 잔존 제거). (high)
- F2 `users.py:60-75` — create_user/register에 IntegrityError→409 가드(중복 이메일 500/경쟁). (high)

**[Area G — 프론트 데이터 정확성/대량 fetch]** (프론트 모듈 8·10·11)
- G1 `Marketing1Dashboard.tsx:121-159` — 주간 KPI 5주차 누락 수정(데이터 주도 WEEKS). (medium, 사용자 체감)
- G2 `ProductsPage.tsx:115-119` — limit 5000 전량 fetch → 서버 필터/페이지네이션, 색상 동적 해시. (high)
- G3 `NasResultItem.tsx:65-86` — `g` 플래그 정규식 stateful test() 하이라이트 버그(lastIndex). (high)
- G4 `MappingTable.tsx:91-98` — 키 입력마다 PATCH+전체 refresh → onBlur/디바운스 + 부분갱신. (high)

### 🟡 MEDIUM

**[Area H — 입력 타입/경계 검증]** (백엔드 모듈 1·2·3) (S-5)
- H1 `dependencies.py:42-49` — JWT sub `uuid.UUID()` 파싱, 실패 시 401. (medium)
- H2 `distribution_customs.py:180-195` — `declaration_id: UUID` 타입 강제(500→404/422). (medium)
- H3 `services/auth.py:9-14` — bcrypt 72바이트 절단 + `UserCreate.password` min/max_length. (medium)
- H4 `models/transaction.py:23-24` — 금액/잔액 상한 검증(<10^13) 또는 Numeric(18,2) 마이그레이션. (medium)
- H5 `upload_history.py:263-270` — upload_id UUID 강제 + 파일명 RFC5987 인코딩(헤더 인젝션). (medium)

**[Area I — path traversal 통일]** (백엔드 모듈 6) (S-6)
- I1 `form_filler/renderer.py:236`,`forms.py:644,1140` — `== real_root or startswith(real_root+os.sep)` 또는 commonpath로 통일. (medium)

**[Area J — 토큰 무효화/세션]** (백엔드 모듈 1·7)
- J1 `auth.py:115-139` — 비번 변경/리셋 시 `password_changed_at`(또는 token_version)로 기존 JWT 무효화. (medium)
- J2 `database.py get_db:11-13` — 예외 시 rollback 후 re-raise 표준 패턴. (medium)
- J3 `services/auth.py:23-24` — decode_token `options={'require':['exp','sub']}`. (medium)

**[Area K — 비동기/확장성]** (백엔드 모듈 3·4)
- K1 `session_service.py:844-983` — send-now를 백그라운드 워커로 위임(202+폴링), 'sending' 고착 회수. (medium)
- K2 `translator.py:51-92` — 빈 레이트버킷 키 제거(메모리 누수). (medium)
- K3 `distribution_customs.py:180` delete — require_admin 또는 soft delete + 행위자 기록. (medium)

**[Area L — 집계/성능 (N+1)]** (백엔드 모듈 2·4·5)
- L1 `sns.py:377-456` — 주차 정의(week_of_month) 단일화, 정수나눗셈 func.floor, KPI 키 불일치 방지. (medium)
- L2 `sns.py:774-813` — stats_growth N+1 → 윈도우 함수. (medium)
- L3 `categories.py:265-300` — 자손 트리 recursive CTE + 단일 UPDATE. (medium)
- L4 `qdrant_search.py:185-264` — 키워드 arm MatchText 인덱스 전환(4000건 scroll 제거). (medium)

**[Area M — 프론트 데이터/UX]** (프론트 모듈 8·10·11)
- M1 `Marketing1Dashboard.tsx:274-299` — 성장률 역산 제거, 실제 prev 합산. (medium)
- M2 `Transactions.tsx:544-584` — 일괄작업 동시성 제한 + allSettled 부분실패 보고. (medium)
- M3 `TransactionImport.tsx:285-296` — confirm payload를 newAccountForm 기준으로, 빈 account_number 차단. (medium)
- M4 `AnalyticsPage.tsx:127-147` — company 필터 실제 전달 또는 Select 비활성. (medium)
- M5 `JobNewPage.tsx:105-121` — setBusy finally 이동(busy 영구 잠금). (medium)
- M6 `nas/Search.tsx:106-139` — load-more를 offset/cursor 증분 + filter 스냅샷 잠금. (medium)

### ⚪ LOW (백로그)
- 에러 메시지 일반화 통일(S-7: `sns.py:984`, distribution 일부) · parse_amount silent 0원(모듈2) · tax_invoice dangling 매칭(모듈2) · CORS 와일드카드 좁히기(모듈7) · 죽은 코드 제거(`_is_table_line` 모듈6, `nodeDepth` 모듈12, 스테일 404 카피) · 하드코딩 외부링크/색상(S-9 모듈8·10) · pptx/agenda 목차 분할(모듈6) · corpus-stats 캐시(모듈5) · 다운로드 FileResponse 스트리밍(모듈6) · MediaGenPanel dedupe(모듈11) 등.

---

## 5. 한 줄 총평

**개별 모듈은 도메인 리스크를 진지하게 다룬 견고한 B급 코드이나, 부서/RAG 인가가 정책·기본값 레벨에서 우회되고(NAS C등급) 전 영역에 테스트 안전망이 사실상 없어, 보안 게이트 공용화와 테스트 인프라 구축이 다른 모든 보완보다 먼저다 — 전체 B−.**


---

# 부록: 모듈별 상세 발견사항


## 백엔드: 인증/사용자/권한 (auth, users, grants, accounts, dependencies, registry, models/schemas) — 등급 B  (정확성6·보안6·유지보수8·성능7·테스트1)

전반적으로 구조가 깔끔하고 권한 모델(부서→모듈 grant + admin 바이패스 + 토큰 사후 무효화)이 일관되며 자기-락아웃 방지·권한상승 차단 등 핵심 가드가 갖춰져 있다. 다만 로그인/가입에 레이트리밋이 전무하고, bcrypt 72바이트 한계·중복 이메일 경쟁/미검증·비-UUID sub 등으로 422여야 할 입력이 500으로 새며, 비번 변경 후 토큰 무효화가 없고 부서 변경 시 user_departments 동기화 누락으로 권한이 잔존하는 정합성 결함이 있다. 인증/인가라는 보안 핵심 모듈인데 전용 테스트가 0건이라는 점이 가장 큰 리스크다.

- **[HIGH]** `backend/app/routers/auth.py:63-89, 29-60` — 로그인·가입 엔드포인트에 레이트리밋이 전혀 없다. 같은 레포의 bank_import 라우터는 check_rate_limit 을 쓰는데 가장 무차별 대입에 취약한 /login, /register 는 무방비라 자격증명 스터핑/계정 열거가 가능하다.
  - 수정: 이미 존재하는 app.services.translation.check_rate_limit(또는 동등 유틸)을 /login(이메일+IP 키, 예: 10회/분)과 /register(IP 키)에 적용. 실패 시 429.
- **[HIGH]** `backend/app/routers/users.py:60-75` — admin create_user 는 이메일 중복 검사가 전혀 없고 IntegrityError 핸들링도 없다. 기존 이메일로 생성 시 DB unique 제약 위반이 그대로 터져 500(+세션 오염)이 난다. register 의 SELECT-후-INSERT 도 동시 요청에 대해 경쟁 조건이 있어 동일하게 500이 날 수 있다.
  - 수정: create_user/register 의 commit 을 try/except IntegrityError 로 감싸 rollback 후 409 반환. register 의 사전 SELECT 는 유지하되 INSERT 도 IntegrityError 가드를 추가(경쟁 대비).
- **[HIGH]** `backend/app/routers/users.py:123-154` — update_user 에서 주 부서(department)만 변경하고 departments 를 보내지 않으면 set_user_departments 가 호출되지 않아 user_departments 에 이전 주 부서가 잔존한다. get_user_modules 는 department ∪ user_departments 합집합이라 사용자가 옛 부서의 모듈 권한을 계속 보유하는 권한 드리프트가 발생한다.
  - 수정: department 가 변경된 경우 departments 가 없어도 set_user_departments(db, user.id, _dept_values(new_department, 기존_extras 또는 [])) 로 재동기화. 최소한 새 주 부서를 user_departments 에 반영하고 옛 주 부서를 제거.
- **[MEDIUM]** `backend/app/dependencies.py:42-49` — JWT sub 가 UUID 형식인지 검증하지 않는다. 위조/손상 토큰의 sub 가 비-UUID 문자열이면 select(User).where(User.id == user_id) 가 Postgres UUID 캐스팅 단계에서 DBAPIError 를 던지는데, 이는 JWTError 가 아니므로 except 에 안 걸려 401 대신 500 이 난다.
  - 수정: user_id 를 uuid.UUID(user_id) 로 파싱하고 ValueError/TypeError 를 401 로 매핑. 파싱 성공분만 쿼리에 사용.
- **[MEDIUM]** `backend/app/services/auth.py:9-14` — bcrypt>=4.0 은 72바이트 초과 비밀번호에 ValueError 를 던진다. 스키마는 비번을 128 '문자'로만 제한하므로 한국어 등 멀티바이트(3바이트/자)면 25자 이상에서 72바이트를 넘겨 422 가 아닌 500 이 발생한다. UserCreate.password 는 길이 제한조차 없다.
  - 수정: hash_password 에서 password.encode()[:72] 로 절단하거나(관용적), 스키마에서 max_length 를 바이트 기준으로 검증. UserCreate.password 에도 min/max_length Field 제약 추가.
- **[MEDIUM]** `backend/app/routers/auth.py:115-139` — 비밀번호 변경(change_password)·관리자 reset 후 기존에 발급된 JWT 가 그대로 유효하다. 토큰에 jti/iat·비번 변경 시각 기반 무효화가 없어, 탈취된 토큰은 비번을 바꿔도 만료(최대 60분~24h)까지 살아 있다.
  - 수정: User 에 password_changed_at(또는 token_version) 컬럼 추가, 토큰에 iat 포함, get_current_user 에서 iat < password_changed_at 이면 401. 최소한 비번 변경 시 access_token 쿠키 즉시 만료 안내.
- **[MEDIUM]** `backend/app/database.py:11-13` — get_db 의존성이 예외 발생 시 명시적 rollback 을 하지 않는다. 라우터 commit 전 예외가 나면 async with 가 세션을 닫긴 하지만, 부분 flush 후 핸들러에서 잡힌 예외(예: IntegrityError 핸들링 누락 지점)와 결합되면 세션 상태 오염·트랜잭션 누수 위험이 있다.
  - 수정: get_db 를 try/except 로 감싸 예외 시 await session.rollback() 후 re-raise 하는 표준 패턴으로 교체.
- **[LOW]** `backend/app/config.py:6` — jwt_secret 기본값이 'change-me' 이고 기동 시 운영에서 기본값이 그대로면 거부하는 어서션이 없다. .env 주입을 잊으면 서명키가 공개 상수가 되어 임의 admin 토큰 위조가 가능하다.
  - 수정: lifespan/startup 에서 settings.jwt_secret in {'change-me',''} 이면 예외로 기동 중단. internal_api_token 도 운영에서 필수화 검토.

## 백엔드: 재무/회계 (transactions, bank_import, attachments, matching, categories, counterparts, balance_snapshots, tax_invoices, upload_history, uploads) — 등급 B  (정확성6.5·보안7.5·유지보수7·성능7·테스트1)

전반적으로 잘 설계된 모듈로, Decimal 정밀도·SHA256 중복차단·partial unique·path traversal 방어·매직바이트 검증·레이트리밋·soft delete 등 회계 도메인 핵심을 진지하게 다뤘고 주석에 과거 CRITICAL/HIGH fix 흔적이 보인다. 다만 수동 매칭의 도메인 불변식 미검증, 레거시 uploads.py의 중복차단 우회, Numeric(15,2) 오버플로우 미처리 등 실제 재현 가능한 정합성 버그가 남아 있고, 재무 모듈 전체에 단위/통합 테스트가 전무하다는 점이 가장 큰 약점이다.

- **[HIGH]** `backend/app/services/matching.py:109-150 (apply_manual_match)` — 수동 매칭이 도메인 불변식을 전혀 검증하지 않는다. find_match_candidates 는 '반대 타입·다른 계좌·동일 금액'을 강제하지만, apply_manual_match 는 클라이언트가 보낸 matched_transaction_id 두 건이 존재/미매칭/삭제안됨만 확인할 뿐 같은 계좌의 두 출금, 금액이 다른 두 건, 같은 타입끼리도 manual 매칭으로 묶어버린다. 잘못된 내부이체 매칭이 들어가 reconciliation/잔액 추이를 오염시킬 수 있고 사용자가 후보 목록을 거치지 않고 임의 ID를 PATCH 하면 그대로 통과한다.
  - 수정: apply_manual_match 내부에서 a.transaction_type != b.transaction_type, a.account_id != b.account_id, a.amount == b.amount 를 검증하고 위반 시 ValueError(→409). 후보 산정 로직과 동일한 술어를 공유 헬퍼로 추출해 단일 진실원으로.
- **[HIGH]** `backend/app/routers/uploads.py:70-96 (upload_transactions)` — 레거시 업로드 경로가 transaction_hash 를 전혀 채우지 않고 dedup 도 하지 않은 채 Transaction(...) 을 add_all 한다. bank_import 가 공들여 만든 (account_id, transaction_hash) partial unique 중복차단을 완전히 우회 → 같은 파일을 이 엔드포인트로 재업로드하면 거래가 전량 중복 적재된다. bank_import.py 와 기능이 중복되는 두 번째 import 코드패스라 유지보수/정합성 양쪽에서 위험.
  - 수정: uploads.py 를 bank_import 오케스트레이터로 통합하거나, 최소한 적재 직전 compute_transaction_hash 로 hash 를 채우고 ON CONFLICT DO NOTHING/사전 조회로 중복을 스킵하도록 통일. 장기적으로는 레거시 엔드포인트 deprecate.
- **[MEDIUM]** `backend/app/models/transaction.py:23-24 (amount/balance Numeric(15,2))` — amount/balance 가 Numeric(15,2) (최대 약 9.99조)인데 parse_amount/Decimal 입력은 무제한 정밀도다. 법인계좌 누적 잔액이나 대형 송금이 10조를 넘으면 DB numeric overflow 로 INSERT 가 500 에러를 내며, bulk_insert 의 except 가 청크 전체를 errors 로 삼켜 부분 적재가 조용히 실패한다. 입력단 상한 검증이 없다.
  - 수정: 스키마(TransactionCreate)·어댑터 단계에서 금액/잔액 절대값 상한 검증(예: < 10^13)을 추가하고 초과 시 명시적 422. 또는 컬럼을 Numeric(18,2) 등으로 확장하는 마이그레이션 검토. bulk_insert 의 광범위 except 도 행 단위 fallback 로 좁힐 것.
- **[MEDIUM]** `backend/app/routers/upload_history.py:263-270 (download_upload_errors), backend/app/routers/transactions.py:278` — Content-Disposition 헤더에 upload_id(경로 str 파라미터, UUID 타입 미강제)를 f-string 으로 그대로 끼워넣는다. CR/LF 또는 따옴표가 포함된 값이면 헤더 인젝션/파일명 스푸핑 여지. transactions download 의 고정 filename 은 안전하나 본 핸들러는 사용자 제어 값이 섞인다.
  - 수정: upload_id 파라미터를 uuid.UUID 타입으로 받아 형식을 강제하고(다른 핸들러는 이미 그렇게 함), 파일명은 ASCII 화이트리스트로 정제 후 RFC5987(filename*) 인코딩 사용.
- **[MEDIUM]** `backend/app/routers/categories.py:265-300 (_max_descendant_depth/_shift_descendant_depth)` — 부모 변경 시 자손 트리를 노드마다 개별 SELECT 로 BFS 순회한다(N+1). depth<=3 으로 폭은 작지만 같은 트리를 두 번(검증+보정) 전체 순회하고, 보정은 ORM 객체를 하나씩 dirty 처리한다. 카테고리 수가 늘면 PATCH 한 번에 다수 왕복.
  - 수정: PostgreSQL recursive CTE 한 방으로 자손 집합을 조회하고, depth 보정은 단일 UPDATE ... WHERE id IN (recursive set) 로 일괄 처리.
- **[MEDIUM]** `backend/tests/:N/A (전 모듈)` — 재무/회계 모듈(transactions, bank_import 어댑터 6종, matching, attachments, categories, counterparts) 전체에 단위/통합 테스트가 0건이다. 해시 정합성, parse_amount 엣지케이스(천단위쉼표/음수/빈셀), 매직바이트 검증, path traversal 방어, ON CONFLICT 중복카운트, 매칭 불변식 등 회귀에 취약한 핵심 로직이 검증 없이 운영된다.
  - 수정: 최소한 (1) compute_transaction_hash 결정성 + transactions/orchestrator 해시 일치, (2) 어댑터별 샘플 xlsx 파싱 골든테스트, (3) attachments 경로검증/매직바이트, (4) 매칭 불변식 위반 거부 pytest 추가. 회계 데이터 특성상 80% 커버리지 목표 권장.
- **[LOW]** `backend/app/services/bank_import/base_adapter.py:42-59 (parse_amount)` — parse_amount 가 파싱 불가/오버플로우 시 예외 대신 조용히 Decimal(0) 을 반환한다. 손상된 금액 셀이 0원 거래로 둔갑하거나(KB 어댑터에서 deposit/withdrawal 모두 0 → continue 로 행 자체가 누락) 적요만 있는 행이 말없이 사라질 수 있다. silent failure.
  - 수정: 파싱 실패를 호출측에 신호(parse_warnings/parse_errors 에 행 단위로 기록)하고, 0원 폴백은 명시적으로 로깅. preview/confirm 에 비정상 행 카운트를 노출.
- **[LOW]** `backend/app/routers/tax_invoices.py:43-56 (link_invoice_to_transaction)` — 송장-거래 연결 시 transaction_id 의 실제 존재 여부를 확인하지 않고 그대로 matched_transaction_id 에 기록한다. 존재하지 않거나 삭제된 거래 ID 를 넣어도 'linked' 를 반환해 dangling 매칭이 생긴다. (FK 가 있으면 무결성 위반 500, 없으면 고아 참조.)
  - 수정: 연결 전 대상 Transaction 존재 + is_deleted=False 확인 후 404/409 반환. 매칭 방향성(이미 다른 송장에 연결됐는지)도 점검.

## 백엔드: 신사업유통(distribution) — 등급 B  (정확성7·보안6·유지보수7·성능6·테스트2)

신사업유통 모듈은 라우터/서비스 책임 분리가 일관되고, 자격증명 암호화(Fernet)·에러 메시지 마스킹·첨부 path traversal 방어·LLM 추출 fallback 등 보안/견고성 의식이 전반적으로 좋다. 다만 LLM 비용을 유발하는 생성 엔드포인트와 면장 삭제가 admin 가드/레이트리밋 없이 모듈 권한만으로 노출되고, 동기 송신 경로가 이벤트루프·DB 트랜잭션을 장시간 점유하며, 테스트는 customs LLM 추출 1개 파일에 그쳐 정산/세션송신/암호화/권한 회귀가 비어 있다. 종합적으로 견고하나 비용 가드와 테스트가 약한 B등급.

- **[HIGH]** `backend/app/routers/distribution.py:219, backend/app/routers/distribution_generate_v2.py:223:219 / 223` — 유료 LLM 호출을 유발하는 /generate-weekly·/generate-custom 이 require_module(DISTRIBUTION) 만 걸려 있고 require_admin·레이트리밋이 없다. 신사업팀 멤버 누구나 페르소나 수만큼 Claude 호출(생성당 N회)을 임의로 트리거할 수 있어 토큰/요금 폭주 + 남용이 가능하다. CLAUDE.md §2가 명시한 '비용 크게 드는 작업' 보호가 엔드포인트 레벨에 없음. 모듈 전체에 rate limiting이 전무하다(common/security.md 'Rate limiting on all endpoints' 위반).
  - 수정: 생성 엔드포인트에 endpoint별 require_admin 추가(또는 별도 'generation' 권한)와 per-user/per-IP 레이트리밋(예: slowapi) 도입. 1요청당 최대 페르소나 수·일일 호출 횟수 캡을 두고 초과 시 429 반환.
- **[MEDIUM]** `backend/app/services/distribution/session_service.py:844:844-983` — send_session_now가 동기 요청 안에서 두 Telethon 클라이언트 연결 + 메시지마다 asyncio.sleep(최대 30s)·typing(최대 5s)·네트워크 송신을 수행하며, 그 사이 세션 객체를 들고 메시지별 db.commit을 반복한다. 메시지 수가 많으면 nginx /api 300s 타임아웃을 넘겨 클라이언트는 끊기지만 서버는 계속 돌고, 타임아웃 시 status='sending'으로 고착될 수 있다. login_manager의 in-memory _store와 함께 uvicorn workers=1 단일 워커 가정에 묶여 수평 확장이 불가능하다.
  - 수정: send-now를 백그라운드 태스크/워커(send_worker.py 경로)로 위임하고 라우터는 즉시 202+세션id 반환 후 폴링하게 한다. 최소한 메시지 수×cap이 타임아웃을 넘지 않도록 총 대기시간 상한을 두고, 'sending' 고착 세션을 회수하는 타임아웃/재처리 로직을 추가.
- **[MEDIUM]** `backend/app/routers/distribution_customs.py:180:180-195` — DELETE /customs/{declaration_id} 가 모듈 권한만 있고 admin 가드가 없다(서비스 delete_declaration도 주석으로 authz 생략 명시). 페르소나 삭제·send-now 등 다른 파괴/위험 작업은 require_admin을 추가했는데 면장 행 삭제는 신사업팀 누구나 가능해 일관성이 깨지고 감사 흔적 없이 통관 데이터가 영구 삭제된다(soft delete 아님).
  - 수정: 삭제 정책을 다른 위험 작업과 통일해 require_admin을 추가하거나, 최소한 soft delete(deleted_at)로 전환하고 삭제 행위자(user_id)를 기록한다.
- **[MEDIUM]** `backend/app/routers/distribution_customs.py:182:182, 190` — declaration_id가 str로 받아져 customs_service.delete_declaration에서 UUID 컬럼(DistributionCustomsDeclaration.id, UUID(as_uuid=True))과 직접 비교된다. 'abc' 같은 비-UUID 문자열이 들어오면 asyncpg가 InvalidTextRepresentation을 던져 404가 아니라 500이 난다(잘못된 id를 정상 404로 처리한다는 의도와 불일치). 입력 검증 경계 누락.
  - 수정: 경로 파라미터 타입을 declaration_id: UUID 로 바꿔 FastAPI가 422로 거르게 하거나, 서비스에서 uuid.UUID(declaration_id) try/except로 변환 실패 시 False(→404) 반환.
- **[MEDIUM]** `backend/tests/distribution/:전체` — 테스트가 test_customs_llm_extractor.py 단 1파일(464줄)뿐이다. 금액/이행률 계산(settlement_service: outstanding, _safe_ratio), 세션 상태머신·send_session_now, 권한 가드(require_module/require_admin), 암호화(encrypt/decrypt round-trip·키 미설정), 시나리오 합성(merge_scenario_contexts step 재번호), customs UPSERT 멱등성에 대한 단위/통합 테스트가 전무하다. 도메인이 금전·실 텔레그램 송신을 다루는데 회귀 안전망이 거의 없다(common/testing.md 80% 기준 대비 매우 미달).
  - 수정: 최소한 settlement 계산·encryption round-trip·세션 상태 전이·customs 멱등 UPSERT에 대한 pytest 단위 테스트와, 권한 가드 통합 테스트(403/admin)를 추가한다.
- **[LOW]** `backend/app/services/distribution/settlement_service.py:126:126-187, 173` — summary()에서 company_label=None이면 cash_flow가 모든 회사 행을 합산한다. total_outstanding = total_kr_purchase 합 - total_deposit_received 합 으로 여러 회사를 단일 외상잔고로 섞는데, 회사별로 통화/스케일이 같다는 암묵 가정이 깨지면 의미가 모호해진다(by_company는 회사 분리해 올바름). 의도된 동작이나 합산 단위가 명시되지 않아 오해 소지.
  - 수정: summary가 전사 합산임을 응답/문서에 명확히 표기하거나, 회사 미지정 시 by_company 결과를 함께 제공해 합산의 단위를 드러낸다.
- **[LOW]** `backend/app/services/distribution/session_service.py:578:578-602` — reject_session의 reason이 로그에만 남고 DB 컬럼이 없어 거부 사유 감사 흔적이 영구 소실된다(주석으로 인지). 검수 거부 사유는 운영상 추적 가치가 있다.
  - 수정: DistributionSession에 reject_reason 컬럼을 추가하거나 별도 감사 로그 테이블에 사유·행위자·시각을 기록한다.
- **[LOW]** `backend/app/routers/distribution_generate_v2.py:289:289-305` — ad_hoc_instruction 사용 시 매 요청마다 active=False '[즉석]' 숨김 시나리오 행을 새로 INSERT한다. 정리(GC) 로직이 없어 반복 호출 시 distribution_scenarios 테이블에 일회성 행이 무한 누적되고, 세션이 RESTRICT FK로 이를 참조해 수동 삭제도 어렵다.
  - 수정: 즉석 지시는 별도 비영속 경로로 처리하거나, 세션에 instruction을 직접 보관하고 더미 시나리오 행 생성을 제거한다. 불가피하면 주기적 정리(미참조 즉석 시나리오 회수) 잡을 둔다.

## 백엔드: SNS/마케팅 (sns.py, review_translation.py, sns_collectors/, sns_importers/, translation/, sns_export.py, models/sns.py, schemas/sns.py) — 등급 B  (정확성7·보안6·유지보수7·성능6·테스트3)

전반적으로 성숙한 모듈이다. SSRF 가드(paging.next 호스트 검증), 토큰 마스킹/appsecret_proof, 멱등 upsert, 계정 단위 실패 격리, nginx 타임아웃을 의식한 페이지 상한 등 운영 경험이 코드에 잘 녹아 있다. 다만 review-translations 목록(GET)이 소유권/부서 필터 없이 전 사용자 번역(원문·캠페인·리뷰어명 등 잠재 민감정보)을 노출하고, 통계 집계에서 주차 정의 불일치 및 N+1, 그리고 댓글/번역의 LLM 레이트리밋 미적용 등 보강할 지점이 있다. 테스트는 순수 헬퍼 중심으로만 존재해 라우터/수집/임포트 경로 커버리지가 매우 낮다.

- **[HIGH]** `backend/app/routers/review_translation.py:141-176` — GET /api/review-translations 목록 엔드포인트가 소유권/부서 필터를 전혀 적용하지 않는다. 단건 GET/PUT/DELETE는 _fetch_or_404에서 본인 또는 admin만 접근하도록 막았지만(H-C1), 목록은 require_module(REVIEW_TRANSLATION) 통과한 모든 사용자(admin + marketing_1 전원)에게 전 사용자의 원문·번역문·캠페인·reviewer_name을 노출한다. search 파라미터로 임의 사용자의 자료를 자유롭게 조회·검색할 수 있어 단건 권한 통제가 사실상 무력화된다. 코드 주석도 'LIST는 별도 정책으로 후속 처리'라고 인정만 하고 미구현 상태다.
  - 수정: 비admin이면 stmt/count_stmt에 .where(ReviewTranslation.created_by_id == user.id)를 추가해 본인 자료만 반환하도록 한다(단건 정책과 동일하게). 부서 공유가 의도라면 그 정책을 명시적으로 코드화하고 주석을 갱신한다.
- **[HIGH]** `backend/app/routers/sns.py:377-456` — stats_weekly의 주차 정의가 스냅샷과 게시물 사이에서 일치하지 않는다. 스냅샷 week_number는 importer가 ISO/엑셀 기준으로 채운 1~5 값인데(WEEK_FOLLOWER_COLUMNS 매핑), 게시물 집계는 week_of_month=((day-1)/7)+1로 계산해 post_map 키를 만든다. 같은 주를 서로 다른 week_number로 분류할 수 있어 snap_rows와 post_map의 (lang,platform,year,month,week) 키가 어긋나면 post_count/view/reaction이 0으로 떨어진다(조용한 오집계). 또한 ((day-1)/7) 정수 나눗셈을 DB에서 cast(Integer)로 처리하는데 dialect에 따라 실수 나눗셈 후 절단 동작이 달라질 수 있다.
  - 수정: 스냅샷과 게시물 양쪽이 동일한 주차 정의(week_of_month)를 쓰도록 단일 소스로 통일하고, 정수 나눗셈은 func.floor((day-1)/7)로 명시한다. KPI 결합 키 불일치 시 게시물 카운트가 유실되지 않도록 outer 결합/검증 테스트를 추가한다.
- **[MEDIUM]** `backend/app/routers/sns.py:774-813` — stats_growth가 계정마다 별도 쿼리(limit 2 스냅샷)를 실행하는 N+1 패턴이다. 활성 계정이 늘면 계정 수만큼 라운드트립이 발생한다. stats_trend/list_post_metrics 등 다른 경로는 단일 쿼리로 처리하는 것과 대비된다.
  - 수정: 윈도우 함수(ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY year,month,week DESC))로 계정별 최신 2건을 한 쿼리에 가져오거나, 전체 스냅샷을 한 번 조회해 파이썬에서 계정별 최신 2건을 추리도록 바꾼다.
- **[MEDIUM]** `backend/app/routers/sns.py:1598-1669` — 댓글 분석(analyze_post_comments)과 번역(translate_post_comments)에는 review_translation에 적용된 사용자별 레이트리밋(check_rate_limit)이 없다. 둘 다 ANTHROPIC_API_KEY로 Claude를 호출(분석=게시물당 1회, 번역=배치 다회)하며 require_module(MARKETING_SNS)만 통과하면 누구나 반복 트리거할 수 있어 토큰/비용 폭주에 노출된다. force=True 재분석/재번역은 캐시 우회까지 가능하다.
  - 수정: translator.check_rate_limit를 이 두 LLM 엔드포인트에도 재사용해 사용자별 호출 상한을 적용하고, force 경로는 더 보수적인 한도를 둔다.
- **[MEDIUM]** `backend/app/services/translation/translator.py:51-92` — 레이트리밋 버킷(_rate_buckets)이 무한 증가한다. user_id별 deque를 만들고 cutoff 이전 항목만 popleft하지만, 더 이상 호출하지 않는 사용자의 빈 deque 엔트리가 영구히 남아 메모리 누수(시간이 지나면 모든 과거 user_id 누적)된다. 단일 인스턴스 장기 구동 시 누적된다.
  - 수정: 버킷이 빌 때 _rate_buckets에서 키를 제거하거나, 주기적으로 비어있는/오래된 버킷을 청소(또는 TTL 캐시/외부 카운터)한다.
- **[MEDIUM]** `backend/app/services/sns_importers/marketing1.py:474-540` — _upsert_posts의 dedup 키가 (account_id, posted_at, title, url)인데 url이 None인 행이 흔하고(엑셀에 링크 미기재), title==NULL 비교는 SQL에서 항상 거짓이라 같은 게시물이 매 import마다 중복 INSERT될 수 있다. 또한 _ensure_accounts/_upsert_*가 모두 commit 없이 진행하고 라우터에서 한 번에 commit하므로, (account_id, posted_at, title, url) UNIQUE 제약이 DB에 없으면 멱등성이 깨진다(주석은 UNIQUE를 가정).
  - 수정: url/ title None을 IS NOT DISTINCT FROM(coalesce) 비교로 처리하거나 external_id 기반 dedup으로 통일하고, 가정한 UNIQUE 제약이 실제 마이그레이션에 존재하는지 확인한다.
- **[LOW]** `backend/app/routers/sns.py:984-986` — ingest/import 등 다수 예외 핸들러가 f-string으로 원본 예외(detail=f"...: {exc}")를 그대로 클라이언트에 반환한다. DB 드라이버 예외 등에 내부 스키마/식별자 등이 섞여 정보 노출이 될 수 있다(import_marketing1_excel 500 경로, collect 500 경로 등). 댓글 분석/번역은 type(exc).__name__만 노출하도록 이미 개선돼 있어 일관성도 떨어진다.
  - 수정: 사용자 노출 detail은 일반화된 한국어 메시지로 고정하고 상세는 logger.exception으로만 남긴다(이미 일부 경로가 쓰는 패턴으로 통일).
- **[LOW]** `backend/app/services/sns_export.py:494-518` — _write_post_row가 '노출수'와 '도달' 두 컬럼 모두 reach_count로 채운다(중복). importer의 HEADER_ALIASES는 reach_count를 '도달'에만 매핑하므로 라운드트립 시 '노출수' 값은 무시되지만, 사람이 보는 시트에선 동일 값이 두 번 나와 혼란을 준다. view_count는 '조회수'로 별도 매핑돼 있어 노출수 칸이 reach인 것은 의미 불명확.
  - 수정: 노출수 칸을 별도 지표(impressions)로 매핑하거나 빈 칸으로 두고, 도달만 reach_count로 채운다.

## 백엔드: NAS검색/RAG (Qdrant 하이브리드 검색 + 리랭커 + 부서 스코핑 + 다운로드) — 등급 C  (정확성7·보안4·유지보수7·성능5·테스트2)

검색 코어(하이브리드 RRF + 관련도 게이트 + cross-encoder 리랭크)는 설계가 정교하고 주석으로 의도가 잘 문서화돼 있으며, 임베더/리랭커/Qdrant 클라이언트의 스레드 안전한 lazy 싱글톤과 동기 클라이언트의 to_thread 오프로드 등 비동기 처리가 견고하다. 다만 보안이 약점이다: 부서 스코핑이 기본 OFF이고, payload의 confidential 플래그를 어디서도 필터링하지 않으며, playground RAG 경로는 부서 스코핑을 통째로 우회한다. 또한 키워드 arm의 scroll 4000건 substring 스캔과 매 검색마다 corpus_stats facet 재조회 등 성능 비효율이 있고, 순수로직(hybrid) 외에는 사실상 테스트가 없다.

- **[HIGH]** `backend/app/services/nas_search/qdrant_search.py:101-133, 164-180` — Qdrant payload에 'confidential' 플래그가 있으나(파일 상단 규약에 명시) vector_arm/keyword_arm/build_qdrant_filter 어디서도 이를 필터링하지 않는다. 기밀로 표시된 문서 청크가 모든 인증 사용자의 검색 결과와 RAG 컨텍스트에 그대로 노출된다.
  - 수정: build_qdrant_filter의 must에 기본적으로 NOT confidential(또는 confidential=false) 조건을 추가하고, 기밀 열람 권한이 있는 role만 예외로 포함시킨다. is_archived도 동일하게 기본 제외 검토.
- **[HIGH]** `backend/app/services/playground/nas_rag.py:37-42` — playground RAG의 search_rag_context가 search_relevant_chunks(query=..., limit=...)를 호출하며 dept_labels를 전혀 전달하지 않는다. nas_search.search_text는 _resolve_dept_scope로 부서 스코핑을 적용하지만, 챗봇 RAG 경로는 사용자 부서·권한과 무관하게 전체 코퍼스(68만 청크)를 검색해 LLM 컨텍스트로 주입한다 → 부서 스코핑 우회.
  - 수정: search_rag_context에 current_user를 받아 nas_search의 _resolve_dept_scope와 동일한 로직으로 dept_labels를 산출해 search_relevant_chunks에 전달. 스코핑 로직을 공용 함수로 추출해 두 경로가 동일 정책을 쓰게 한다.
- **[MEDIUM]** `backend/app/config.py:87` — nas_dept_scoping_enabled 기본값이 False다. 따라서 _resolve_dept_scope가 항상 None(전체검색)을 반환해 모든 사용자가 전 부서 코퍼스를 검색·다운로드할 수 있다. 부서 격리가 코드로 구현돼 있어도 운영 기본값에서 비활성이라 실효가 없다.
  - 수정: 운영에서 기본 활성(True)으로 전환하거나, 최소한 매핑이 없는 부서를 전체검색으로 폴백하는 보수적 동작(_resolve_dept_scope 274-275행)을 '결과 없음'으로 바꿔 권한 누수를 막는다. 활성 여부와 무관하게 confidential 게이트는 항상 적용.
- **[MEDIUM]** `backend/app/routers/nas_search.py:468-481` — download_file_by_path는 부서 스코핑·confidential 검증 없이 허용 루트(_DOWNLOAD_ROOTS, /mnt/nas-rw RW 마운트 포함) 안이기만 하면 임의 path를 전 직원에게 내려준다. 검색 권한과 다운로드 권한이 분리돼 있어, 사용자가 경로 문자열만 알면(또는 추측하면) 부서·기밀 범위를 넘어 원본 파일을 받을 수 있다.
  - 수정: 다운로드 시에도 path로 Qdrant payload(dept/confidential)를 조회해 호출자 권한과 대조하거나, 검색 결과에 서명된 단기 다운로드 토큰을 발급해 임의 경로 접근을 차단한다. RW 마운트(/mnt/nas-rw)를 다운로드 허용 루트에 둔 것도 재검토.
- **[MEDIUM]** `backend/app/services/nas_search/qdrant_search.py:185-264` — 키워드 arm이 풀텍스트 인덱스 부재로 매 검색마다 scroll로 최대 nas_keyword_scan_limit(4000)건 payload(text 포함)를 끌어와 파이썬에서 substring 매칭한다. 대용량 text payload 4000건 전송+디코드는 검색당 무시 못 할 I/O·CPU 비용이며, 필터가 약하면(부서 미지정) 코퍼스 앞부분만 스캔해 recall도 편향된다.
  - 수정: 인덱싱 파이프라인에 text payload 인덱스(MatchText)를 추가해 query_filter로 전환(파일 상단 주석의 미결 과제). 과도기에는 scan_limit를 낮추고 path/파일명만 우선 매칭하거나 with_payload를 필요한 키로 한정해 전송량을 줄인다.
- **[LOW]** `backend/app/routers/nas_search.py:92-127` — /corpus-stats와 /depts가 매 호출마다 corpus_stats()로 Qdrant facet(limit=50)을 재집계한다. 대시보드·필터 옵션은 자주 바뀌지 않는데 캐시가 없어 호출마다 Qdrant 왕복이 발생한다.
  - 수정: 짧은 TTL(예: 60s) 인메모리 캐시 또는 lru_cache+타임스탬프로 facet 결과를 캐싱해 반복 집계를 피한다.
- **[LOW]** `backend/app/routers/nas_search.py:437-461` — download_file(by id) 엔드포인트는 require_module(NAS_SEARCH)만 거치고 별도 사용자 의존성이 없어 file_id로 nas_files 행을 찾으면 부서·기밀 무관하게 다운로드된다. 또한 nas_files 테이블은 레거시 인덱서 제거로 사실상 미적재라 항상 404일 수 있어(죽은 경로) 혼란을 준다.
  - 수정: by-path 경로로 일원화하고 dept/confidential 인가를 추가하거나, 미사용이면 엔드포인트를 제거해 죽은 코드를 정리한다.
- **[LOW]** `backend/tests/nas_search:test_hybrid.py 전체` — 테스트가 hybrid.py 순수함수(토큰화/RRF/like_escape)에만 존재한다. search_text의 관련도 게이트·키워드 강매칭 판정·리랭크 폴백·부서 스코프 교집합(_effective_dept_labels)·path traversal(_is_path_within_root) 같은 보안·정확성 핵심 분기에 대한 테스트가 전무하다.
  - 수정: _effective_dept_labels(교집합/폴백), _is_path_within_root(상위경로 prefix 충돌·symlink), _keyword_is_strong, romanize_hangul에 대한 단위 테스트를 추가(모두 외부 의존 없이 가능). 최소한 보안 경계 함수부터 커버.

## 백엔드: 문서작업(docgen) — routers/{docgen,documents_admin,forms}.py, services/{docgen,documents,form_filler,llm}/, schemas/{docgen,documents_admin,form_filler} — 등급 B  (정확성7·보안6·유지보수7·성능6·테스트1)

전반적으로 잘 구조화된 LLM 문서생성/양식채움 모듈이다. 환각 방어 가드레일(출처 화이트리스트·confidence 임계·토큰 grounding), best-effort NAS 저장, prompt caching, 검수 강제 상태전이 등 도메인 리스크를 진지하게 다룬 흔적이 분명하다. 다만 RAG 검색이 부서 스코핑 없이 전사 코퍼스를 조회하는 점(잠재적 부서간 정보 노출), path-traversal 검사의 separator 누락, 그리고 가드레일·마크다운 파서·렌더러 등 최고위험 로직에 대한 테스트가 전무한 점이 종합 등급을 끌어내린다.

- **[HIGH]** `backend/app/services/documents/sources.py:59-61` — collect_sources 의 RAG 경로가 search_relevant_chunks(query=..., limit=...) 를 dept_labels 없이 호출한다. bridge.search_relevant_chunks 는 dept_labels=None 이면 부서 필터를 걸지 않으므로, 어떤 사용자의 문서생성/섹션재생성/검수든 전사 NAS 코퍼스 전체를 검색한다. 부서 권한이 분리된 환경에서 타 부서 기밀 문서 내용이 생성 결과·출처 목록(DocSourceRef.path)으로 유출될 수 있다. forms.py 의 attach_nas_sources 도 동일하게 dept_labels 미전달.
  - 수정: current_user.department(또는 권한 부서 라벨 목록)를 collect_sources/attach 경로까지 전파해 search_relevant_chunks/search_per_variable 의 dept_labels 인자로 넘긴다. 관리자만 전사 검색을 허용하려면 분기.
- **[MEDIUM]** `backend/app/services/form_filler/renderer.py:236` — path-traversal 방어가 real_target.startswith(real_root) 로 separator 없이 비교한다. real_root='/var/lib/form_filler/outputs' 일 때 '/var/lib/form_filler/outputs-evil/x.docx' 같은 형제 디렉토리가 prefix 매치로 통과한다. forms.py:644(_save_upload_file), forms.py:1140(download_job) 도 동일 패턴. nas_output.py:101 만 올바르게 real_root+os.sep 을 쓴다. 현재 파일명이 정화되어 직접 익스플로잇은 어렵지만 심층방어가 깨져 있다.
  - 수정: 세 곳 모두 real_target == real_root or real_target.startswith(real_root + os.sep) 로 통일(os.path.commonpath 사용도 가능).
- **[MEDIUM]** `backend/app/services/form_filler/renderer.py:137-145` — _replace_in_paragraph 가 변수 치환 시 전체 텍스트를 runs[0] 에 몰아넣고 나머지 run.text 를 모두 비운다. 한 단락 안에 굵게/색상 등 서로 다른 서식 run 이 섞여 있으면 첫 run 의 서식이 단락 전체에 강제 적용되어 서식이 파괴된다. PRD FR-06 의 '표/이미지/글꼴 100% 보존' 수용기준과 정면 충돌하며, 변수가 없던 부분의 서식까지 망가진다.
  - 수정: 치환된 run 만 in-place 패치하거나, run 경계를 넘는 매치에 한해서만 병합하도록 범위를 좁힌다. 최소한 변경되지 않은 텍스트의 run 서식은 유지.
- **[MEDIUM]** `backend/app/routers/docgen.py:213-234, 271-289` — regenerate_section 와 review 엔드포인트는 LLM 호출 비용/토큰(_cost, model)을 받지만 form_jobs 에 전혀 영속화하지 않는다(generate 만 _persist_generate_job 수행). 따라서 documents_admin /usage 의 비용·토큰 집계가 재생성·검수 호출만큼 구조적으로 과소집계된다. 코드 주석도 'v1 미반영'이라 인지된 부채지만, 관리자 비용 패널을 신뢰 불가하게 만든다.
  - 수정: regenerate/review 도 best-effort 잡 영속화(kind 구분 또는 별도 회계 행)를 추가하거나, 최소한 usage 응답에 '미집계 호출 존재' 한계를 명시.
- **[MEDIUM]** `backend/app/services/docgen/markdown_blocks.py:45-47` — _is_table_line 은 어디서도 호출되지 않는 죽은 코드이며, 동시에 버그를 품고 있다: line.strip().startswith(("|", "")) 에서 빈 문자열 "" 는 항상 True 라 조건 전체가 무의미. 유지보수자가 이 함수를 재사용하면 잘못된 표 판정을 하게 된다.
  - 수정: 미사용 함수 _is_table_line 삭제. 표 판정은 실제 사용되는 parse_blocks/_looks_like_table 로 일원화.
- **[LOW]** `backend/app/routers/forms.py:1149` — download_job 이 Path(real_target).read_bytes() 로 파일 전체를 메모리에 로드한 뒤 BytesIO 로 StreamingResponse 를 만든다. docx 가 커지면 워커 메모리를 통째로 점유하며 스트리밍 이점이 사라진다(동일 패턴이 docgen render 에도 있으나 거긴 in-memory 생성이라 불가피).
  - 수정: FileResponse(real_target, media_type=..., filename=...) 로 교체해 OS 레벨 스트리밍 위임.
- **[LOW]** `backend/app/services/docgen/pptx_builder.py:147-170` — _agenda_slide 가 headings 를 줄당 0.62인치로 무한 나열한다. 섹션이 많은 문서(8개 이상 권장이지만 LLM 이 더 낼 수 있음)면 목차 항목이 슬라이드 하단/밖으로 흘러넘쳐 잘린다. 본문 슬라이드는 _MAX_TEXT_LINES/_MAX_TABLE_ROWS 로 분할하는데 목차만 캡이 없다.
  - 수정: 목차도 페이지당 항목 수 상한을 두고 넘으면 다음 슬라이드로 분할(본문과 동일 정책).
- **[LOW]** `backend/app/services/form_filler/guardrails.py:28` — _KOREAN_PROPER_PATTERN 의 직책 접미사 그룹이 모두 optional((?:...)?)이라 사실상 2~6자 한글 단어 전부를 '고유명사 후보'로 본다. verify_token_grounding 의 50% 일치 게이트와 결합되면 일반 한국어 본문에서 grounding 거부/통과가 토큰 추출 노이즈에 크게 휘둘려, 정상 값을 누락 보강 큐로 떨어뜨리는 false negative 가 잦을 수 있다.
  - 수정: 고유명사 후보를 직책 접미사가 실제 붙은 경우나 사전/엔티티 신호가 있는 경우로 좁히고, paraphrase 허용을 위해 LLM-judge 보강(주석에 예정으로 명시됨)을 앞당긴다.

## 백엔드: 코어 인프라/마이그레이션 (config, database, dependencies, main, logging_setup, models, alembic/versions) — 등급 B  (정확성7·보안5·유지보수7·성능6·테스트2)

코어 인프라는 전반적으로 견고하다. 마이그레이션 체인(001→034)은 완전히 선형이고 브랜치/중복 head 없이 모든 리비전에 downgrade가 대칭으로 구현돼 있으며, async 세션·lifespan 정리·인가 캐시 폴백·constant-time 내부토큰 비교 등 좋은 패턴이 보인다. 다만 (1) DB 엔진에 pool_pre_ping/recycle이 없어 배포 시 Postgres 재시작 후 stale 커넥션 에러 위험, (2) jwt_secret이 'change-me'로 기본값이고 기동 시 검증이 없는 insecure-by-default, (3) 코어 인프라 테스트가 사실상 0(인증/세션/마이그레이션 미커버)이 주요 약점이다.

- **[HIGH]** `backend/app/config.py:5-7, 239-242` — insecure-by-default 시크릿: jwt_secret 기본값이 'change-me', database_url에 password 평문 기본값. Settings()는 기동 시 이들 값이 기본값인지 검증하지 않아, .env 주입이 누락된 환경(테스트/오설정 컨테이너)에서 예측가능한 키로 JWT가 위조 가능해진다. 인증 전체가 이 비밀에 의존한다.
  - 수정: Settings에 model_validator(mode='after')를 추가해 운영 모드에서 jwt_secret in {'change-me',''} 또는 database_url이 기본값이면 RuntimeError로 fail-fast. 최소한 main lifespan 시작 시 assert/raise로 검증.
- **[HIGH]** `backend/app/database.py:7` — create_async_engine에 pool_pre_ping / pool_recycle 미설정. 배포가 tk101-postgres 컨테이너를 재시작(운영 메모리상 deploy=docker compose up -d --build)하면 풀에 남은 stale 커넥션이 다음 요청에서 'connection was closed' 에러로 첫 요청들을 실패시킨다.
  - 수정: engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True, pool_recycle=1800). 필요 시 pool_size/max_overflow도 명시.
- **[MEDIUM]** `backend/app/routers/auth.py:80-85` — access_token 쿠키가 secure=False로 발급(코드 주석상 호스트가 평문 HTTP). httpOnly+samesite=strict이긴 하나, 평문 전송 구간에서 JWT 탈취 가능. dependencies._extract_token이 쿠키 폴백을 지원하므로 쿠키가 실제 인증 경로다.
  - 수정: 운영 호스트에 HTTPS(리버스 프록시 TLS) 적용 후 secure=True로 전환. 전환 전까지는 토큰 만료를 짧게(access_token_expire_minutes) 유지.
- **[MEDIUM]** `backend/app/main.py:148-154` — CORSMiddleware가 allow_credentials=True와 함께 allow_methods=['*'], allow_headers=['*'] 사용. 쿠키 기반 인증과 결합 시, CORS 화이트리스트(cors_origins)에 신뢰 출처만 있어야 안전한데 와일드카드 메서드/헤더는 공격면을 넓힌다. 또한 상태변경 엔드포인트에 별도 CSRF 토큰이 없어 samesite=strict 쿠키에만 의존한다.
  - 수정: allow_methods/allow_headers를 실제 사용하는 집합으로 좁히고, cors_origins 기본값('http://localhost:5173')이 운영에서 .env로 반드시 override되는지 기동 검증 추가. 쿠키 인증 상태변경 경로에 CSRF 방어 명시.
- **[MEDIUM]** `backend/app/services/auth.py:23-24` — decode_token이 algorithms=[settings.jwt_algorithm]만 지정하고 require/audience 등 클레임 강제가 없다. python-jose는 exp를 기본 검증하나, 'sub' 누락은 dependencies에서 사후 None 체크로만 잡힌다. 토큰 검증 정책이 분산되어 있다.
  - 수정: jwt.decode(..., options={'require': ['exp', 'sub']})로 필수 클레임을 디코드 단계에서 강제하고, 가능하면 audience/issuer를 발급·검증 양쪽에 추가.
- **[MEDIUM]** `backend/tests/:전반` — 코어 인프라(get_current_user/require_admin/require_module 인가, get_db 세션, 마이그레이션 up/down 라운드트립, config 검증)에 대한 테스트가 사실상 0. 존재하는 테스트는 sns/nas_search/distribution 일부뿐. 인증·인가는 보안 핵심인데 회귀 안전망이 없다.
  - 수정: pytest+httpx로 (1) 만료/위조/비활성 계정 토큰 거부, (2) require_module 부서 grant 매트릭스, (3) alembic upgrade head→downgrade base→upgrade 라운드트립을 tk101_dev에서 도는 통합테스트 추가.
- **[LOW]** `backend/app/main.py:126, 141` — lifespan 정리 코드에서 except (asyncio.CancelledError, Exception)로 광범위 포착(noqa BLE001). 워밍업/미디어 태스크 정리 시 모든 예외를 무음 처리해, cancel 외 실제 정리 실패가 로그 없이 삼켜진다.
  - 수정: 최소한 logger.exception으로 남기거나, CancelledError만 잡고 그 외는 logger.warning 후 진행.
- **[LOW]** `backend/app/modules/registry.py:_user_departments` — for ud in (user.departments or []) 주변을 bare except Exception: pass로 감싸 detached 상태를 무음 처리. lazy='selectin'로 보통 eager load되지만, 예외를 완전히 삼키면 부서 일부 누락→권한 축소가 조용히 발생할 수 있다.
  - 수정: except를 좁혀(SQLAlchemy DetachedInstanceError 등) 명시 처리하고 debug 로그를 남겨 권한 누락이 드러나게 한다.

## 프론트: 마케팅/대시보드 (frontend/src/pages/marketing, pages/dashboards, components/sns, api/sns.ts) — 등급 B  (정확성7·보안5·유지보수7·성능6·테스트1)

전반적으로 잘 짜인 antd v6 + recharts 대시보드 모듈로, Promise.allSettled 기반 위젯 격리·취소 토큰·null 안전 포매터 등 견고한 패턴이 일관되게 적용되어 있다. 다만 사용자/관리자/엑셀임포트가 제공한 URL을 스킴 검증 없이 href로 렌더링하는 저장형 XSS 표면, 관리자 대시보드의 하드코딩된 http:// 외부 링크(혼합콘텐츠·동적설계 위반), 그리고 마케팅1 KPI 피벗의 5주차 누락 같은 실제 결함이 있다. 이 모듈군에 대한 단위/통합 테스트가 사실상 0건이라 회귀 안전망이 없다.

- **[HIGH]** `frontend/src/pages/marketing/SnsAccounts.tsx:287-294 (page_url <a href>), and SeoulSns.tsx:363 / Marketing1Dashboard.tsx:549-558 (post url)` — 계정 page_url·게시물 url 을 스킴 검증 없이 그대로 href 로 렌더링한다. 엑셀 임포트(importMarketing1Excel)·수동 콘텐츠 등록·계정 등록은 임의 문자열을 받으므로 `javascript:alert(1)` 같은 값이 저장되면 링크 클릭 시 스크립트가 실행되는 저장형 XSS 가 가능하다. 어디에도 sanitize/new URL 검증이 없다.
  - 수정: 렌더 직전 URL 스킴을 http/https 로 화이트리스트 검증하는 헬퍼(safeHref)를 만들어 통과 못하면 링크를 비활성/평문 처리. 입력단(폼·임포트)에서도 zod 등으로 http(s) 만 허용. 추가로 SeoulSns.tsx:363 의 target=_blank 에 rel="noopener noreferrer" 보장.
- **[MEDIUM]** `frontend/src/pages/dashboards/AdminDashboard.tsx:57-76 (EXTERNAL_LINKS)` — Open WebUI/Langfuse 링크가 http://43.155.202.112:3000, :3001 로 하드코딩되어 있다. HTTPS 페이지에서 http 링크는 혼합콘텐츠/브라우저 차단을 유발하고, IP·부서·서비스 하드코딩 금지(CLAUDE.md 동적설계 원칙)에도 위반된다. 서버 IP 변경 시 깨진다.
  - 수정: n8n 처럼 nginx 리버스 프록시 상대경로(/openwebui/, /langfuse/)로 통일하거나 환경변수/백엔드 설정에서 베이스 URL 을 주입. 최소한 https 로 전환.
- **[MEDIUM]** `frontend/src/pages/dashboards/Marketing1Dashboard.tsx:121-159 (pivotWeeklyRows), 139-142` — 주간 KPI 피벗이 week_number 1~4 만 처리하고 5주차(월 5주가 걸치는 달) 팔로워를 조용히 버린다. 같은 레포의 SnsContentStatus·WeeklyPostCountRow 는 week5 를 다루므로 모듈 간 불일치이며, 5주차가 있는 달에는 KPI 표/합계가 실제와 달라진다.
  - 수정: PivotedRow 와 buildTotalRow 에 week5 를 추가하고 컬럼·합계에 반영하거나, 주차 컬럼을 동적으로 생성(WEEKS 배열 순회)해 데이터 주도로 만든다.
- **[MEDIUM]** `frontend/src/pages/dashboards/Marketing1Dashboard.tsx:274-299 (computeTotals)` — 총 성장률을 실제 prev 팔로워 합으로 계산하지 않고, 이미 반올림된 per-platform growthRate 로부터 followers/(1+growthRate) 로 prev 를 역산한다. growthRate 가 0(=prev 합이 0이었던 플랫폼)이면 prev=현재값으로 처리되어 성장률이 희석되고, 역산은 부동소수 오차에 취약하다. aggregateByPlatform 이 이미 prevByPlatform 합을 갖고 있는데 버려서 중복·취약 로직이 됐다.
  - 수정: aggregateByPlatform 에서 PlatformSummary 에 prevFollowers(실제 직전 합)를 함께 보관하고, computeTotals 는 sum(prev)/sum(current) 로 직접 성장률 산출. 역산 제거.
- **[MEDIUM]** `frontend/src/pages/marketing (전체) + dashboards:package.json test=vitest, 대상 모듈 .test.* 0건` — 마케팅/대시보드/SNS 모듈 전체에 단위·통합 테스트가 없다(레포에서 유일한 테스트는 forms/DocGenPage.test.tsx). pivotWeeklyRows·aggregateByPlatform·computeTotals·getCellValue·buildAccountLabel 등 순수 변환 로직은 테스트하기 쉬운데도 회귀 안전망이 전무하다.
  - 수정: 최소한 순수 함수(pivot/aggregate/totals/getCellValue/buildAccountLabel/isConnectedAccount)에 대한 vitest 단위 테스트 추가. 5주차·null 팔로워·prev=0 등 엣지케이스 포함.
- **[LOW]** `frontend/src/api/sns.ts:279-294 (downloadXlsx)` — blob 다운로드 시 서버가 Content-Disposition 으로 보낸 파일명을 무시하고 항상 클라이언트 fallbackName 을 쓴다. 또한 에러 응답(JSON detail)이 responseType:blob 이면 blob 으로 와서 catch 의 extractErrorDetail 이 detail 을 못 읽고 일반 메시지만 노출한다.
  - 수정: 응답 헤더 content-disposition 파싱해 우선 사용. 블롭 에러는 await err.response.data.text()→JSON.parse 로 detail 복원하는 분기 추가.
- **[LOW]** `frontend/src/pages/marketing/SnsContentStatus.tsx:313 (rowKey=row.account_id), 189-204` — WeeklyPostCountRow 에 고유 id 가 없어 account_id 를 rowKey 로 쓰는데, 백엔드 집계가 동일 account_id 를 (예: 브랜드/언어 분리로) 중복 반환하면 React key 충돌이 난다. 또 합계 컬럼 render(202-203)는 isTotalRow 분기 양쪽이 동일 <strong> 출력이라 분기가 무의미한 죽은 코드.
  - 수정: rowKey 를 안정적 합성키(`${account_id}-${platform}-${language}`)로. 합계 컬럼의 중복 분기 제거.
- **[LOW]** `frontend/src/pages/marketing/PostMetricsDrawer.tsx:84-86, 159-162` — useState 초기값으로 post?.comment_summary 를 쓰지만 Drawer 가 상시 마운트(open prop 제어)라 첫 마운트 시 post=null → 초기 summary 가 항상 null. 실제 동기화는 165-168 effect 가 담당하므로 84-86 초기화는 사실상 무효(혼동 유발). 댓글 탭은 activeTab 의존이라 게시물 전환 후 같은 탭이면 재조회되어 정상이나, 초기 state 코드가 오해를 부른다.
  - 수정: 초기값을 null 로 두고 동기화는 effect 단일 책임으로 명확히 하거나, 주석으로 effect 가 진짜 소스임을 명시.

## 프론트: 재무 (frontend/src/pages/finance, components/finance, 재무 API) — 등급 B  (정확성7·보안5·유지보수8·성능6·테스트1)

재무 프론트엔드는 antd 기반으로 구조가 깔끔하고, 에러 처리/로딩 상태/금액 포맷/중복 import 방어 등 실무 디테일이 잘 잡혀 있어 유지보수성은 우수하다. 다만 인증 토큰을 localStorage에 보관(XSS 노출)하고 일괄 작업이 무제한 병렬 요청을 쏘며 부분 실패를 조용히 가리는 등 보안·견고성 약점이 있고, 포매팅·import 플로우 같은 핵심 로직에 대한 테스트가 errorUtils 하나를 빼면 사실상 전무하다.

- **[HIGH]** `frontend/src/api/client.ts:10-16` — 인증 access token을 localStorage에서 읽어 Bearer 헤더로 부착한다. 주석은 httpOnly 쿠키 인증을 표방하지만 실제로는 토큰이 localStorage에 평문 저장되어 어떤 XSS든 토큰을 탈취·외부 전송할 수 있다. 재무(계좌·거래·금액) 모듈은 민감도가 높아 영향이 크다.
  - 수정: 가능하면 토큰을 httpOnly+SameSite 쿠키로만 전송하고 localStorage 저장/Bearer 부착을 제거한다(주석대로 쿠키가 1차 인증이면 localStorage 경로는 불필요). 유지가 불가피하면 최소한 짧은 만료+리프레시, 그리고 web/security.md의 CSP를 운영에 강제해 XSS 표면을 줄인다.
- **[MEDIUM]** `frontend/src/pages/Transactions.tsx:544-584` — handleBulkCategory/handleBulkMemo/handleBulkDelete가 선택된 행(최대 pageSize 200건)에 대해 Promise.all로 PATCH/DELETE를 무제한 병렬 발사한다. 200개 동시 요청은 브라우저/백엔드를 압박하고, 일부만 실패해도 catch에서 단일 '일괄 실패' 메시지만 띄운 뒤 전체 refetch하여 어떤 건이 적용/미적용인지 사용자가 알 수 없다(부분 실패 은폐).
  - 수정: 동시성 제한(예: p-limit 또는 청크 배치)으로 묶고, 백엔드에 일괄 PATCH 엔드포인트가 있으면 단일 호출로 대체한다. allSettled로 성공/실패 건수를 분리해 '180건 성공·20건 실패'처럼 보고한다.
- **[MEDIUM]** `frontend/src/pages/finance/TransactionImport.tsx:285-296` — create_new 경로에서 account_holder가 메타에 없으면 '미지정', account_number가 없으면 빈 문자열을 그대로 백엔드로 전송해 신규 계좌를 만든다. 사용자에게 보여준 편집 폼(newAccountForm) 값은 confirm payload에 전혀 반영되지 않고 preview.account_meta만 사용하므로, 폼에서 수정해도 무시되고 placeholder 데이터로 계좌가 생성될 수 있다(재무 마스터 오염).
  - 수정: confirm payload를 row.newAccountForm 기준으로 구성하거나, 폼이 '참고용'이라면 필수값 누락 시 confirm을 막고 사용자에게 보완을 요구한다. account_number 빈 문자열로의 계좌 생성을 클라이언트에서 차단한다.
- **[MEDIUM]** `frontend/src/components/finance/TransactionFormModal.tsx:133-145` — 금액 InputNumber에 formatter만 있고 parser가 없으며, 입금/출금 구분만 받고 금액 부호·소수/통화 검증이 없다. 외화 계좌(USD 등)도 라벨이 '금액 (원)'로 고정이고 step=1000으로 원화 가정이 박혀 있어 외화 거래 수동 등록 시 부적절하다. amount=0 입력도 통과한다(min=0).
  - 수정: min을 1 이상(또는 양수 검증 rule 추가)으로 두고, 계좌 통화에 따라 라벨·step·소수 자리수를 동적으로 바꾼다. formatter와 짝이 되는 parser를 명시해 antd 버전 변경에도 콤마 파싱이 깨지지 않게 한다.
- **[LOW]** `frontend/src/pages/finance/MatchingWorkbook.tsx:35-40` — formatAmount가 parseFloat 실패 시 NaN을 검사하지 않아 '+NaN'/'-NaN'을 표시할 수 있고, 백엔드 amount가 이미 부호를 포함한 경우 type 기반 부호와 이중으로 어긋날 수 있다(절댓값+type부호 가정).
  - 수정: Number.isFinite 가드를 추가해 비정상 값은 '-' 처리하고, 부호 규칙을 한 곳(공용 util)으로 모아 Transactions/MatchingWorkbook/Modal 간 일관성을 보장한다.
- **[LOW]** `frontend/src/components/finance/MatchingCandidatesModal.tsx:44-52` — accountLabel이 렌더마다 accounts.find로 O(n) 선형 탐색을 한다. MatchingWorkbook도 동일. 후보가 많고 계좌가 많으면 렌더당 O(후보수×계좌수)가 된다. Transactions.tsx는 이미 Map을 쓰는데 컴포넌트 간 패턴이 불일치한다.
  - 수정: accounts를 Map(id->account)으로 한 번 만들어 조회를 O(1)로 바꾸고, 라벨 포맷 헬퍼를 공용화한다.
- **[LOW]** `frontend/src/pages/finance/UploadHistory.tsx:386-396` — errors.download_url을 검증 없이 <Button href> target=_blank로 연결한다. 백엔드가 신뢰 경로지만, 만약 download_url이 javascript:나 외부 도메인일 경우 클릭 시 위험할 수 있다(rel=noreferrer는 있으나 스킴 검증은 없음).
  - 수정: href에 사용하기 전 https/상대경로 화이트리스트 스킴만 허용하도록 검증한다(AttachmentModal item.url에도 동일 적용).
- **[LOW]** `frontend/src/utils/errorUtils.test.ts:전체` — 재무 모듈 관련 자동화 테스트가 errorUtils.test.ts 단 하나뿐이다. formatAmount/formatBalance/formatKRW 같은 금액 포맷 로직, import preview/confirm 중복 방어, 부분 실패 처리, 권한(admin) 분기 등 회귀 위험이 큰 로직에 단위 테스트가 전무하다.
  - 수정: 우선 순수 함수(금액 포맷·KRW 축약·tail4·formatSize)와 readyRows/resultSummary 같은 파생 로직에 vitest 단위 테스트를 추가하고, 핵심 플로우(import 중복 confirm 방어, 일괄 부분 실패)에 컴포넌트 테스트를 더한다.

## 프론트: 신사업유통 (distribution) — pages/distribution, components/distribution, api/distribution* — 등급 B  (정확성7.5·보안7·유지보수7·성능6·테스트0)

전반적으로 잘 구조화된 antd 기반 어드민 UI다. API 레이어가 타입으로 명확히 분리되어 있고, 에러 처리는 공통 extractErrorDetail로 일관되며, 라우트는 ProtectedRoute(module="distribution")로 게이팅하고 위험 액션(send-now/페르소나 관리)은 isAdmin으로 UI에서 숨겨 백엔드 require_admin과 방어를 이중화했다. 다만 이 모듈에 대한 테스트가 전무하고(0점), ProductsPage의 5000행 전량 fetch + 전부 클라이언트 집계와 브랜드/카테고리 색상 하드코딩(동적 설계 원칙 위반)이 눈에 띈다. critical 수준 결함은 발견되지 않았다.

- **[HIGH]** `frontend/src/pages/distribution/ProductsPage.tsx:115-119, 39-68` — 전체 명품재고를 limit 5000으로 한 번에 받아와 회사/브랜드/카테고리/검색/집계를 전부 클라이언트에서 수행한다. 4개사 풀 적재가 가정 2000행을 넘어 5000에 근접하면 페이로드·메모리·렌더가 급증하고, 5000 초과 행은 조용히 누락되어 통계가 틀어진다(상단 KPI/회사별 합계가 부분 데이터 기준이 됨). 또한 BRAND_COLOR/CATEGORY_COLOR가 루이비통/고야드 등으로 하드코딩되어 CLAUDE.md의 '계정/브랜드 하드코딩 금지(동적 설계)' 원칙을 위반한다.
  - 수정: 서버 측 필터·페이지네이션·집계 엔드포인트로 전환(이미 listProducts가 company_label/brand/category/search 파라미터를 지원하므로 이를 사용)하거나 최소한 total을 받아 5000 초과 시 경고를 노출하라. 색상은 브랜드별 결정적 해시(예: 문자열→팔레트 인덱스)로 동적 산출해 새 브랜드 자동 반영.
- **[HIGH]** `frontend/src/pages/distribution/* (전 모듈), frontend/src/api/distribution*.ts:n/a` — 이 모듈(페이지 10개·모달 6개·API 5개, 약 8800줄)에 대한 단위/통합/E2E 테스트가 전혀 없다. 정산 합계 누적, 관세 역산(실가=신고가÷0.75) 표시, 누적 send_after_sec 오프셋, ratioPercent/formatMoney 같은 금액·비즈니스 로직 유틸이 회귀 보호 없이 노출되어 있다.
  - 수정: 최소한 순수 유틸(formatMoney/formatNumber/ratioPercent/formatCumulativeOffset, SettlementPage summary 누적, recoveredGap 계산)에 대한 vitest 단위 테스트와 핵심 플로우(세션 승인/거부/송신 버튼 노출 조건) 컴포넌트 테스트를 추가하라.
- **[MEDIUM]** `frontend/src/api/client.ts:10-16` — withCredentials(httpOnly 쿠키)가 1차 인증인데도 access token을 localStorage에도 저장하고 Authorization 헤더로 보낸다. localStorage 토큰은 XSS로 탈취 가능하며, 쿠키만으로 충분하다면 토큰 이중 저장은 공격면을 넓힌다. 이 모듈의 모든 distribution 호출이 이 클라이언트를 공유한다.
  - 수정: httpOnly 쿠키를 단일 소스로 삼고 localStorage 토큰을 제거하거나, 부득이하면 sessionStorage/메모리 보관으로 노출 창을 줄여라(공유 인프라이므로 모듈 외 영향 검토 필요).
- **[MEDIUM]** `frontend/src/pages/distribution/AnalyticsPage.tsx:127-147, 854-859` — company 필터를 RangeFilter.company_label로 만들어 전달하지만 분석 탭들(getCostByDay/getCostByPersona/getSessionStatusCounts 등)은 from/to만 사용하고 company는 전혀 넘기지 않는다. 즉 회사 Select는 실제로 데이터를 거르지 못하고, 사용자에게 '미지원 시 전체 반환될 수 있음'이라는 모호한 경고만 띄운다 → 운영자가 회사별 비용/실패를 본다고 오인할 위험.
  - 수정: 백엔드 analytics 엔드포인트에 company_label를 실제로 전달·필터링하도록 연결하거나, 미지원이면 Select 자체를 비활성/숨김 처리해 오인을 차단하라.
- **[MEDIUM]** `frontend/src/components/distribution/GenerateTriggerModal.tsx:194-198, 342-345` — 주석/라벨은 '한국 어드민 + 자격증명 보유만 노출'이라고 하지만 실제 loggedInPersonas는 역할 무관 is_logged_in만 필터한다(코드가 정답, 주석이 stale). 운영자가 발신 후보를 잘못 이해해 베트남 계정을 발신자로 고를 수 있다. 기능 자체는 백엔드가 검증하지만 라벨/주석 불일치가 혼란을 유발한다.
  - 수정: 186번 줄 주석과 402-403 라벨을 현재 동작('로그인된 모든 역할')과 일치시키고, 정말 역할 제한이 필요하면 필터에 role 조건을 명시하라.
- **[LOW]** `frontend/src/pages/distribution/* (다수):n/a` — antd의 static message.error / Modal.error / Modal.warning를 전역으로 직접 호출한다(SessionDetailPage 717-731 등). antd v6에서 static API는 ConfigProvider 테마·로케일·다크모드 컨텍스트를 받지 못해 공식적으로 App.useApp() 사용을 권장한다. 일관성·테마 적용에 영향.
  - 수정: App.useApp()의 { message, modal } 인스턴스를 사용하도록 점진 마이그레이션하라.
- **[LOW]** `frontend/src/pages/distribution/CustomsPage.tsx:338-361` — 삭제 컬럼에서 Popconfirm을 deletingId!==null로 disabled 처리하지만, 첫 삭제 진행 중 다른 행의 Popconfirm은 비활성화되어도 동일 행 재클릭/UX가 다소 불명확하다. 동시 삭제 가드는 동작하나, 진행 중 표시(전역 로딩)와 행 단위 disabled 조합이 직관적이지 않다.
  - 수정: 삭제 진행 중에는 테이블 전체에 가벼운 로딩 오버레이를 주거나, 진행 행만 스피너 + 나머지 버튼 비활성으로 상태를 명확히 하라(현재도 기능상 문제는 없음).
- **[LOW]** `frontend/src/api/distribution.ts:604-625` — uploadMessageAttachment의 docstring은 '최대 20MB'라고 적혀 있으나 실제 백엔드 config(distribution_attachment_max_bytes)와 프론트 가드(SessionDetailPage 329)는 200MB다. 문서/주석이 실제 한도와 10배 어긋나 운영자 오해 소지.
  - 수정: docstring을 200MB(또는 config 값 참조)로 정정하라. 코드 동작은 정상.

## 프론트: 문서/폼/NAS/플레이그라운드 (documents, forms, nas, playground) — 등급 B  (정확성6.5·보안6.5·유지보수7.5·성능6.5·테스트2.5)

전반적으로 잘 구조화되고 일관된 antd 기반 프론트엔드로, 멀티파트 업로드·검색 필터·JWT 인증 blob 다운로드·폴링 정리(unmount cleanup) 등 까다로운 부분을 신중하게 처리했고 None/falsy/취소 가드도 대체로 충실하다. 다만 검색 하이라이트의 stateful 정규식 버그와 매핑 테이블의 키 입력마다 서버 PATCH+전체 refresh를 트리거하는 패턴 등 실제 사용성·성능에 직결되는 결함이 있고, 두 개 파일을 제외하면 테스트가 사실상 없어 회귀 안전망이 부족하다. critical은 없으나 사용자 체감 가능한 high 2건을 우선 수정 권장.

- **[HIGH]** `frontend/src/pages/nas/NasResultItem.tsx:65-86` — highlightSnippet가 `g` 플래그 정규식(pattern)을 split 후 동일 객체로 `.map()` 안에서 `pattern.test(part)`를 호출한다. `g` 플래그 정규식의 test()는 lastIndex를 전진시켜 상태를 보존하므로, 매칭 토큰에 대해서도 호출 순서에 따라 true/false가 번갈아 잘못 나온다. 결과적으로 검색어 하이라이트(<mark>)가 일부 매칭 토큰에서 누락되거나 비매칭 텍스트에 잘못 적용된다.
  - 수정: map 내부에서 stateful test()를 쓰지 말 것. tokens Set으로 part 자체를 비교하거나(`tokens.some(t => t.toLowerCase()===part.toLowerCase())`), 매 part마다 `pattern.lastIndex=0`을 리셋하거나, `g` 없는 별도 정규식으로 판정한다. idx 대신 안정 key 사용도 권장.
- **[HIGH]** `frontend/src/components/forms/MappingTable.tsx:91-98 (+ JobMappingPage.tsx:91-98 handleValueChange)` — 값 컬럼 Input의 onChange가 키 입력 한 글자마다 onValueChange→`patchJobMapping`(서버 PATCH) + `await refresh()`(잡 전체 재조회)를 호출한다. 매 타건마다 네트워크 왕복 N+1 + 전체 detail 재렌더가 발생해 입력 지연·포커스 유실·중간 글자 손실 위험이 크고, 빠른 타이핑 시 응답 순서 경합으로 값이 되돌아갈 수 있다.
  - 수정: Input을 로컬 상태(또는 비제어)로 두고 onBlur/onPressEnter 또는 디바운스(예: 400ms) 시점에만 PATCH하도록 변경하고, PATCH 성공 시 전체 refresh 대신 해당 매핑만 부분 갱신(immutable map)한다.
- **[MEDIUM]** `frontend/src/pages/forms/JobNewPage.tsx:105-121` — handlePickUpload에서 `await refresh()`가 try 밖에 있고 `setBusy(false)`가 finally가 아니라 함수 끝줄에 위치한다. refresh()가 throw하면 setBusy(false)에 도달하지 못해 busy가 영구 true로 남아 '자료 추가'·'매핑 실행' 버튼이 비활성 잠금된다. 또한 부분 실패 시 사용자에게는 업로드 실패만 보이고 refresh 실패는 무시된다.
  - 수정: 업로드+refresh 전체를 try로 감싸고 setBusy(false)를 finally로 옮긴다. refresh 실패도 message로 표면화.
- **[MEDIUM]** `frontend/src/api/client.ts:10-16` — 인증 토큰을 localStorage에 저장하고 모든 요청 헤더에 주입한다. withCredentials로 httpOnly 쿠키도 함께 보내므로 localStorage 토큰은 XSS 노출 표면을 추가로 늘릴 뿐이다(antd/사용자 텍스트가 dangerouslySetInnerHTML 없이 렌더되므로 즉각적 XSS는 안 보이나, 토큰 탈취 시 영향이 큼). 401 인터셉터가 하드 `window.location.href` 리다이렉트만 수행해 진행 중이던 입력/상태가 통째로 유실된다.
  - 수정: 가능하면 쿠키 단일 인증으로 통일하고 localStorage 토큰 의존 제거. CSP 강화(rules/web/security.md)와 함께 토큰 저장 표면 최소화. 리다이렉트 전 현재 경로를 returnTo로 보존.
- **[MEDIUM]** `frontend/src/pages/nas/Search.tsx:106-139` — '더 보기'가 limit을 늘려 매번 처음부터 전체를 재검색(searchNasText)하고 results를 통째로 교체한다. 페이지네이션이 아니라 누적 재조회라 동일 상위 결과를 반복 전송·재정렬하며, 그 사이 filter가 바뀌면 submittedQuery와 현재 filter가 불일치해 사용자가 본 결과와 다른 집합이 섞일 수 있다. SEARCH_LIMIT_MAX(50) 상한도 작아 cursor/offset 페이징 부재가 드러난다.
  - 수정: 백엔드에 offset/cursor 페이징을 도입해 증분 append로 전환하거나, 최소한 load-more 시 현재 filter 스냅샷을 함께 잠가(submitted filter 보관) 일관성을 보장한다.
- **[MEDIUM]** `frontend/src/pages/forms (전체) · frontend/src/pages/playground (전체):-` — 스코프 내 테스트가 nasUtils.test.ts(순수 유틸)와 DocGenPage.test.tsx(렌더 스모크 2건) 단 둘뿐이다. 멀티파트 업로드, 검색 필터 파라미터 빌드(buildSearchParams/periodToMtimeFrom), confirmMappingsBeforeRender의 필수-누락 로직, 폴링 상태 전이, 다운로드 fallback 등 회귀 위험이 높은 분기 로직에 단위 테스트가 전무하다. common/testing.md의 80% 기준 대비 크게 미달.
  - 수정: 최소한 periodToMtimeFrom·buildSearchParams·confirmMappingsBeforeRender·groupTasksByDate·formatMetricsLine 등 순수 함수에 vitest 단위 테스트를 추가하고, MappingTable 입력→PATCH 흐름과 SourcePicker 선택 로직에 RTL 상호작용 테스트를 도입.
- **[LOW]** `frontend/src/components/playground/MediaGenPanel.tsx:180-213, 228-277` — useEffect 안에서 startPolling을 호출하지만 deps에서 startPolling을 eslint-disable로 제외하고, startPolling은 매 렌더 새로 생성되는 클로저(kind 캡처)다. 또한 onSubmit에서 새 task를 prepend하면서 taskId 중복(서버가 동일 task_id 반환 시) 가드가 없어 동일 키 카드가 중복될 수 있다.
  - 수정: startPolling을 useCallback으로 안정화하거나 ref에 담고, setTasks prepend 시 기존 taskId 존재 여부를 확인해 중복을 제거(dedupe)한다.
- **[LOW]** `frontend/src/pages/playground/AdminSessionsPage.tsx:188-198` — 초기화 버튼이 setUserId/''·setQuery('') 후 setTimeout(...,0)으로 fetchSessions를 호출한다. 상태 비동기성을 setTimeout으로 우회하는 취약한 패턴으로, fetchSessions가 클로저로 잡은 직전 값에 의존하지 않아 우연히 동작하지만 의도가 불명확하고 깨지기 쉽다.
  - 수정: fetchSessions를 (userId,q) 인자형으로 리팩터해 명시적으로 빈 값으로 호출하거나, 초기화 의도를 useEffect([resetToken])로 표현한다.

## 프론트: 코어(라우팅/공통/API) — 등급 B  (정확성7·보안5·유지보수8·성능8·테스트3)

라우팅·모듈 권한 게이팅·사이드바 빌드·에러 추출 유틸이 일관되고 타입이 탄탄하며, modules.tsx의 데이터 주도 NAV 구성과 카테고리별 자동 숨김 로직이 특히 깔끔하다. 다만 JWT를 localStorage에 중복 저장해 httpOnly 쿠키의 XSS 방어를 스스로 무력화하는 점, 인증 사용자용 catch-all(404) 라우트 부재로 알 수 없는 경로가 빈 레이아웃을 렌더하는 점, 그리고 코어(ProtectedRoute/useAuth/client 인터셉터)에 대한 테스트가 사실상 전무한 점이 약점이다.

- **[HIGH]** `frontend/src/api/client.ts / pages/Login.tsx / api/playground.ts:275:client.ts:11, Login.tsx:17` — 백엔드가 httpOnly access_token 쿠키를 지원(withCredentials:true)함에도 동일 JWT를 localStorage('token')에 저장하고 모든 요청에 Bearer로 동봉한다. localStorage 토큰은 임의 XSS(서드파티 스크립트, 의존성 침해 등)로 탈취 가능하므로 httpOnly 쿠키의 보호가 무력화된다. 토큰이 client/Login/useAuth/playground 4곳에 흩어져 결합도도 높다.
  - 수정: 인증을 httpOnly 쿠키 단일 채널로 통일하고 localStorage 토큰 저장/Bearer 주입을 제거한다(쿠키만으로 인증). 즉시 제거가 어렵다면 최소한 CSP를 강제하고, streamChat/window.open 흐름만 쿠키 폴백을 쓰도록 좁힌다.
- **[MEDIUM]** `frontend/src/App.tsx:384-391` — 인증된 사용자 분기(AppLayout 하위)에 catch-all(path="*") 라우트가 없다. 비인증 분기(393행)에만 존재하므로, 로그인한 사용자가 오타/구버전 링크로 미등록 경로에 접근하면 어떤 Route에도 매칭되지 않아 레이아웃 안이 빈 화면으로 렌더된다.
  - 수정: 인증 분기 마지막에 <Route path="*" element={<Navigate to="/" replace />} /> 또는 전용 NotFound 페이지를 추가한다.
- **[MEDIUM]** `frontend/src/api/client.ts:18-27` — 401 응답 인터셉터가 요청 종류와 무관하게 window.location.href='/login'으로 전체 페이지를 하드 리다이렉트한다. 백그라운드 폴링/부수적 요청 하나가 401을 받아도 사용자가 작업 중이던 화면이 통째로 날아갈 수 있고, SPA 라우터 상태가 초기화된다. 또한 401→localStorage 제거→/login 이동 로직이 client.ts·useAuth.logout·useAuth.checkAuth 3곳에 중복돼 있다.
  - 수정: 401 처리를 단일 핸들러(예: onUnauthorized 콜백/이벤트)로 모으고, 가능하면 react-router navigate를 쓰거나 현재 경로가 이미 /login이면 리다이렉트를 생략한다. 토큰 정리/로그아웃 흐름을 한 곳으로 통합한다.
- **[LOW]** `frontend/src/pages/Login.tsx:17-20` — login 성공 후 onLogin()(=checkAuth, 비동기 getMe 호출)을 await 없이 호출하고 곧바로 navigate('/')를 실행한다. user 상태가 채워지기 전에 '/'로 이동하면 App의 user 게이트가 잠깐 비어 깜빡임/추가 리다이렉트가 발생할 수 있다(현재는 App이 user truthy일 때만 보호 라우트를 그리므로 동작은 하지만 경합 의존적).
  - 수정: checkAuth를 await한 뒤 navigate 하거나, login 응답의 토큰 저장 후 user를 즉시 set하는 경로를 마련해 경합을 제거한다.
- **[LOW]** `frontend/src/pages/settings/CategoryPage.tsx:55-69` — nodeDepth의 첫 for 루프(root에서 직접 매칭 시 1 반환)는 이어지는 findDepth(root, id, 1)가 동일 결과를 내므로 죽은 코드다. 또한 CategoryPage/CounterpartPage/UploadHistory/TransactionImport 4곳에 '백엔드 라우터 미등록 (Wave 5 예정)' 404 메시지가 그대로 남아 있어(이미 라우터 존재) 사용자에게 오해를 줄 수 있는 스테일 카피다.
  - 수정: nodeDepth의 선행 루프를 삭제해 findDepth 단일 경로로 정리하고, 스테일한 404 statusMessages 카피를 현재 동작에 맞게 갱신/제거한다.
- **[LOW]** `frontend/src/components/ProtectedRoute.tsx / hooks/useAuth.ts:전체` — 코어 보안·라우팅 로직(ProtectedRoute 모듈 게이팅, useAuth의 checkAuth/logout, client 인터셉터의 401 처리, modules.tsx buildSidebarMenuItems 권한 필터)에 대한 단위 테스트가 전무하다. 레포 전체 *.test 파일은 3개(errorUtils, DocGenPage, nasUtils)뿐이며 코어는 미커버다.
  - 수정: buildSidebarMenuItems(권한별 그룹 숨김/멀티부서), ProtectedRoute(허용/비허용 module), useAuth(토큰 없음/getMe 실패 시 정리)에 대한 vitest 단위 테스트를 추가한다. 이들은 순수 로직이라 비용 대비 회귀 방어 효과가 크다.