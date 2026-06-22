# TK101 코드 품질/아키텍처 리뷰 스코어카드 (2026-06-22)

> 멀티에이전트 품질 리뷰(보안/버그와 다른 렌즈): 12모듈 6차원(architecture·simplicity·consistency·readability·modularity·testability). Run wf_35bf4e6b.


I'll write the quality scorecard directly based on the review JSON provided. No tools needed.

# TK101 코드베이스 품질 스코어카드

리뷰 대상: 12개 모듈 / 6차원 점수(architecture·simplicity·consistency·readability·modularity·testability) / 등급 B~C

---

## 1. 전체 품질 점수표

| # | 모듈 | Arch | Simpl | Consist | Read | Modul | Test | 등급 |
|---|------|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| 1 | BE: 인증/사용자/권한 | 8 | 6 | 6 | 8 | 6 | 7 | **B** |
| 2 | BE: 재무/회계 | 7 | 6 | 5 | 7 | 6 | 6 | **B** |
| 3 | BE: 신사업유통 | 6 | 6 | 7 | 7 | 5 | 6 | **B** |
| 4 | BE: SNS/마케팅 | 5 | 5 | 6 | 6 | 5 | 5 | **C** |
| 5 | BE: NAS검색/RAG | 7 | 6 | 6 | 7 | 6 | 7 | **B** |
| 6 | BE: 문서작업(docgen) | 7 | 6 | 6 | 6 | 6 | 6 | **B** |
| 7 | BE: 코어 인프라 | 7 | 6 | 5 | 7 | 6 | 6 | **B** |
| 8 | FE: 마케팅/대시보드 | 7 | 7 | 5 | 6 | 6 | 5 | **B** |
| 9 | FE: 재무 | 7 | 6 | 6 | 7 | 6 | 5 | **B** |
| 10 | FE: 신사업유통 | 6 | 5 | 5 | 6 | 4 | 5 | **C** |
| 11 | FE: 문서/폼/NAS/플레이그라운드 | 7 | 6 | 5 | 7 | 5 | 5 | **B** |
| 12 | FE: 코어(라우팅/공통/API) | 6 | 5 | 4 | 6 | 5 | 4 | **C** |
| | **평균(단순)** | **6.7** | **5.8** | **5.5** | **6.7** | **5.5** | **5.6** | |

### 차원별 평균 (낮은 순)
- consistency **5.5** ← 최약점
- modularity **5.5**
- testability **5.6**
- simplicity **5.8**
- readability **6.7**
- architecture **6.7** ← 최강점

### 전체 품질 등급

가중치: architecture ×2.0, simplicity ×1.8, 나머지(consistency·readability·modularity·testability) 각 ×1.0. (장인정신 리뷰이므로 구조 건전성과 단순성에 가중)

- 가중합 = 6.7×2.0 + 5.8×1.8 + 5.5 + 6.7 + 5.5 + 5.6 = 13.4 + 10.44 + 23.3 = **47.14**
- 가중치 총합 = 2.0 + 1.8 + 4.0 = 7.8
- **가중평균 = 6.04 / 10**

> **전체 품질 등급: B−**
> 설계 골격(architecture 6.7)과 가독성은 건전하나, consistency·modularity·testability가 5점대에 묶여 등급을 끌어내린다. "구조는 옳게 잡혔는데 마감(중복 제거·경계 정리·테스트 분리)이 빚으로 쌓인" 전형적 상태다. 보안 리뷰와 동일한 B−이지만 성격이 다르다(아래 5절 대비).

---

## 2. 모듈 랭킹

### 가장 잘 짜인 모듈 (Top 3)
1. **BE: 인증/사용자/권한 (B, arch 8)** — 라우터/서비스/모델/의존성 레이어 분리가 가장 명확. 동기·캐시 인가, 선언적 `require_module` 게이팅, 비자명 결정의 근거 주석이 모범적. 단 하나의 high(권한 진실원천 이중화)만 닫으면 A급.
2. **BE: NAS검색/RAG (B, test 7)** — `hybrid.py`를 DB/네트워크 의존 없는 순수함수로 떼어내 테스트성을 의식한 설계. lazy-load 스레드세이프 싱글톤 일관성, 검색 품질 결정에 상수+근거 주석.
3. **BE: 재무/회계 (B)** — Protocol+registry 어댑터 플러그인 구조, frozen DTO 불변성 강제, flush/commit 트랜잭션 경계 규약. 설계 의도는 최상급이나 중복(해시 3벌·평행 파이프라인)이 등급을 눌렀다.

### 가장 손봐야 할 모듈 (Bottom 3)
1. **FE: 코어(라우팅/공통/API) — C, consistency 4 / testability 4 (최하위)** — 38개 수동 라우트 블록(NAV_ITEMS와 이중 진실원천), API 반환 컨벤션 혼재, `extractErrorDetail` 래퍼 5곳 복붙(+스테일한 "Wave 5" 문구 프로덕션 유출). 골격은 건전하나 마감이 가장 부족.
2. **FE: 신사업유통 — C, modularity 4 (최하위)** — 포맷터 8개 페이지 복붙, 상태 라벨/색상 3곳에 서로 다른 hex, 회사 집계 로직 4회 재구현, 800줄 초과 3파일, 하드코딩 "래더엑스" 기본값(동적설계 위반).
3. **BE: SNS/마케팅 — C, architecture 5 (전 모듈 최저 arch)** — `sns.py` **2181줄**(한도 3배)에 SQL집계·엑셀피벗·수집오케스트레이션·LLM분석 전부 응집. week_of_month 3중 복붙, LLM 접근 경로 이원화로 비용추적/캐싱이 한쪽만 적용.

---

## 3. 아키텍처 테마 (핵심 — 모듈 횡단 반복 패턴)

리뷰 전반에서 **같은 5가지 구조적 결함이 모듈을 가리지 않고 반복**된다. 개별 모듈 문제가 아니라 팀 차원의 패턴 부재다.

### 테마 A — 거대 파일 / 응집도 붕괴 (가장 광범위)
800줄 한도를 넘긴 파일이 양 스택에 걸쳐 다수. 한 파일에 비즈니스로직·스키마·테이블정의·프레젠테이션이 과적재.
- `routers/sns.py` **2181줄**(한도 3배) — 최악
- `routers/forms.py` 1350줄, `playground.py` 1412줄, `transactions.py` 779줄(근접)
- `session_service.py` 997줄, `config.py` 260줄 god-object(9개 트랙 90개 설정)
- FE: `Marketing1Dashboard.tsx` 888줄, `Transactions.tsx` 1115줄, `SessionDetailPage.tsx` 1070줄, `MediaGenPanel.tsx` 849줄
→ **영향**: 탐색·리뷰·테스트·변경 안전성 전부 저하. consistency·modularity 점수 하락의 주범.

### 테마 B — 라우터/컴포넌트로의 비즈니스 로직 누수
HTTP 경계여야 할 라우터(BE)와 표현이어야 할 컴포넌트(FE)에 핵심 도메인 로직이 인라인됨 → 단위 테스트 불가.
- BE: `nas_search.search_text`(랭킹 파이프라인 120줄), `sns.py`(SQL집계·피벗 인라인, 라우트끼리 직접 호출로 레이어 경계 붕괴), `transactions.py`(집계 SQL 본문 작성), `forms.py`(매핑 영속화·상태전이), `distribution_generate_v2.py`(오케스트레이션 150줄 핸들러)
- FE: `Marketing1Dashboard`(가중평균·성장률 역산이 비-export 로컬함수), `DocGenPage`(검수→재생성 매핑 로직)
→ **영향**: testability 5.6의 직접 원인. "순수 변환을 컴포넌트/라우터 밖으로" 가 공통 처방.

### 테마 C — 중복 로직 / DRY 위반 (모든 모듈에 존재)
같은 코드가 2~8곳에 복붙되어 드리프트가 이미 시작된 사례 다수.
- BE: 거래 해시 SHA256 **3벌**(드리프트 시 dedup 조용히 깨짐), 엑셀 임포트 **파이프라인 2벌 평행 공존**, week_of_month 식 3중, 6개 은행 어댑터 골격 복붙, rate-limit 상수 2곳 동일정의, user-or-404 블록 5회
- FE: blob 다운로드 시퀀스 **7곳**(이미 `removeChild` vs `a.remove()` 드리프트 발생), 포맷터 8곳, `extractErrorDetail` 래퍼 5곳, 상태 라벨/색상 3곳
→ **영향**: simplicity·modularity 동시 하락. 한 곳 고치면 나머지 누락되는 회귀 위험이 누적됨.

### 테마 D — 일관성 없는 에러처리 + 컨벤션 혼재 (consistency 5.5의 핵심)
- BE: 에러 메시지 한/영 혼재(`tax_invoices`/`uploads`만 영어), 경로 파라미터 `str` vs `uuid.UUID` 혼용, 응답 스키마 위치(schemas/ vs 파일내 BaseModel) 불일치, "삼킴 vs 502 전파" 폴백 정책이 함수마다 다름
- FE: API 반환이 `res.data` 언랩 vs raw `AxiosResponse` 혼재, 공용 `extractErrorDetail` 있는데도 손수 캐스팅, 기본 언어 'ko' vs 'zh' 화면마다 불일치
→ 동일 도메인에서 사용자에게 **다른 색/다른 표기/다른 동작**이 보이는 수준까지 진행.

### 테마 E — 추상화 빈틈: 데드코드(YAGNI 위반) + 하드코딩(동적설계 위반)
- 데드코드: `file_walker.py` 191줄 전체 미사용, `LLMResult`/`JobStatusUpdate`/`_is_table_line`, `_fetch_recent_video_ids`, 동일 삼항 데드분기(FE)
- 하드코딩(CLAUDE.md 동적설계 원칙 직접 위반): `DEPARTMENT_MODULES` 폴백 매트릭스, `DISTRIBUTION_ACTIVE_ACCOUNT_LABELS=('VN-A','KR-A1')`, 회사명 "래더엑스" 기본값(BE+FE 양쪽)
- 추상화 부재: 서버상태를 useState/useEffect 수동관리(TanStack Query 미도입)가 FE 전반에 반복

---

## 4. 리팩토링 우선순위 (영향/효과 큰 순 · 영역별 묶음 — 병렬 에이전트 배분용)

### P0 — 즉시(정확성/원칙 위반 동반, 작은 변경으로 큰 효과)

| # | 작업 | 모듈/파일 | 효과 |
|---|------|----------|------|
| P0-1 | **권한 진실원천 단일화** — DEPARTMENT_MODULES 폴백 제거, lifespan에서 grant캐시 fail-fast | BE인증 `modules/registry.py` | 인가 정확성 + 동적설계 원칙 회복 (high) |
| P0-2 | **거래 해시 단일 util화** — account_id 기반 1개로 통일, 어댑터 raw_hash·compute_hash 제거 | BE재무 `bank_import/base_adapter.py`·`orchestrator.py`·`transactions.py` | dedup 조용한 파손 차단 (high) |
| P0-3 | **하드코딩 제거** — "래더엑스" 기본값, ACTIVE_ACCOUNT_LABELS 화이트리스트를 데이터 제어로 | BE유통 `generation_service.py` · FE유통 `distribution_generate.ts`·`CustomsPage.tsx` | 오적재 방지 + 원칙 준수 |
| P0-4 | **품질버그 + 유출 문자열** — `fileIconType`에 name 전달, "Wave 5" 메시지 일반 404로 교체 | FE `nas/Search.tsx:222` · FE settings 5파일 | 분류 정확성 + 내부맥락 유출 차단 |

### P1 — 거대 파일 분할 + 로직 하강 (병렬 가능, 에이전트 1파일씩 배분)

| # | 작업 | 모듈/파일 |
|---|------|----------|
| P1-1 | `sns.py` 2181줄 → 도메인별 라우터 분할 + 집계를 `services/sns_stats.py`로 | BE SNS |
| P1-2 | `forms.py` 1350줄 → 스키마 이관 + 라우터 분할 + 보조함수 서비스 하강 | BE docgen |
| P1-3 | `transactions.py` 집계 3종 → `services/transaction_reports.py`, 매칭 라우터 분리 | BE재무 |
| P1-4 | `config.py` god-object → CoreSettings + 트랙별 BaseSettings 서브클래스(env_prefix) | BE코어 |
| P1-5 | `Marketing1Dashboard.tsx`·`Transactions.tsx`·`SessionDetailPage.tsx`·`MediaGenPanel.tsx` → transforms/columns/presentational 분리 | FE 4파일 |

### P2 — 공용 유틸 추출(DRY) — 가장 비용대비 효과 큰 묶음

| # | 작업 | 위치 |
|---|------|------|
| P2-1 | FE `triggerBlobDownload(blob, filename)` 단일화(7곳 교체) | `utils/download.ts` |
| P2-2 | FE 포맷터 통합(formatNumber/Date/Money/KRW)·FINANCE_COLORS·주차도메인(`lib/weeks.ts`) | `utils/format.ts` 등 |
| P2-3 | FE `extractErrorDetail` 래퍼 5곳 제거, 프리셋 팩토리화 | `utils/errorUtils.ts` |
| P2-4 | BE user-or-404 / get_transaction_or_404 Depends화, `_no_whitespace`·PasswordStr Annotated 별칭 | BE인증·재무 |
| P2-5 | BE week_of_month_expr() 단일화, NAS bridge dept필터·scroll버킷 헬퍼화 | BE SNS·NAS |
| P2-6 | BE 6개 은행 어댑터 → 선언적 컬럼스펙 + 템플릿 메서드로 보일러플레이트 제거 | BE재무 `adapters/*` |

### P3 — 일관성/플랫폼 정리 (점진)

| # | 작업 | 위치 |
|---|------|------|
| P3-1 | BE 에러 detail 한국어 통일, 경로 파라미터 `uuid.UUID` 통일, 응답 스키마 위치 규약 단일화 | BE재무 전반 |
| P3-2 | FE API 반환 컨벤션 통일(`res.data` 언랩) + 라우트 데이터주도화(NAV_ITEMS 단일소스) | FE코어 `App.tsx`·api/* |
| P3-3 | FE 서버상태 TanStack Query 도입(useState/useEffect 보일러플레이트 제거) | FE재무·유통·settings |
| P3-4 | BE 모델 ID/timestamp 규약 단일 base 믹스인 통일 + `models/__init__` 누락 4클래스 등록 | BE코어 |
| P3-5 | 데드코드 제거(`file_walker.py`, `LLMResult`, `_fetch_recent_video_ids` 등) + LLM 접근경로 `call_claude`로 일원화 | BE NAS·docgen·SNS |

> **병렬 배분 가이드**: P1은 파일 단위 독립이라 5개 에이전트 동시 투입 가능. P2는 유틸 추출 후 호출부 교체라 "추출 1 + 교체 N" 순차 의존 — 추출을 먼저 머지하고 교체를 분산. P0은 정확성 영향이 있어 P1/P2 착수 전 우선 처리.

---

## 5. 한 줄 총평 + 보안 리뷰 대비

**총평**: "**설계는 B+로 옳게 잡혔으나 마감이 C로 빚을 쌓아 전체 B−**" — 레이어링·플러그인 구조·순수함수 분리 같은 골격 판단은 장인급인데, 거대 파일·라우터 로직 누수·복붙·일관성 부재라는 **반복되는 마감 결함**이 모든 모듈에 균일하게 깔려 있다. 단일 모듈의 재앙이 아니라 팀 차원의 규율(파일 한도·DRY·레이어 경계) 미집행 문제다.

**보안 리뷰(B−)와의 대비**:
- **같은 등급, 다른 성질**. 보안 B−는 "개별 취약점"의 합이지만, 품질 B−는 "**구조적 패턴의 반복**"이다.
- 보안 결함은 **국소적·점적**(해당 지점만 패치)이나, 품질 결함은 **횡단적·체계적**(같은 처방을 N곳에 적용)이라 리팩토링이 본질적으로 병렬화·일괄화에 적합하다.
- 흥미롭게도 **두 리뷰가 같은 파일을 공유**한다: `dependencies.py`·`config.py`·인증/권한 모듈은 보안 하드닝(JWT fail-fast, 상수시간 비교)이 잘 박힌 동시에 품질 최상위권 — 즉 **보안을 의식한 곳이 품질도 높다**. 반대로 품질 최하위(FE코어·SNS·FE유통)는 보안 관점에서도 401 하드리다이렉트·토큰 이중모델 같은 경계 누수가 겹친다.
- **결론**: 품질 리팩토링(P0-1 권한 단일화, P3-2 인증 토큰 단일화)이 보안 부채와 직접 교차하므로, **품질·보안을 같은 작업으로 묶으면 양쪽 B−를 동시에 끌어올릴 수 있다.**


---

# 부록: 모듈별 품질 발견사항


## 백엔드: 인증/사용자/권한 (auth/users/grants/accounts, dependencies, registry, models/schemas) — 등급 B  (arch8·simpl6·consist6·read8·modul6·test7)

전반적으로 레이어링이 깔끔한 모듈이다. 라우터는 얇고, 암호/JWT(services/auth), 부서동기화(department_sync), 인가 계산(modules/registry), DI 가드(dependencies)로 책임이 잘 분리되어 비즈니스 로직이 라우터에 거의 새지 않는다. 다만 (1) 권한 진실의 원천이 동적 grants 테이블과 하드코딩 DEPARTMENT_MODULES 폴백으로 이중화되어 있고(CLAUDE.md 동적설계 위반·divergence 위험), (2) users.py의 user-or-404 조회와 schemas의 _no_whitespace 검증이 여러 곳에 복붙되어 DRY가 약하며, (3) 쿠키 만료(24h 하드코딩)와 JWT 만료(config 60분)가 어긋나는 등 일관성·단순성에서 감점 요소가 있다.

- 👍 라우터/서비스/모델/의존성 레이어 분리가 명확하다. 라우터는 검증·조회·응답에 집중하고, 해싱·토큰·부서동기화·모듈인가는 전부 services/modules로 빠져 있어 비즈니스 로직 누수가 거의 없다.
- 👍 인가 모델이 사려깊다. get_user_modules가 동기·캐시 기반이라 매 요청 인가에서 DB 왕복이 없고, require_module 팩토리로 라우터 단 게이팅을 선언적으로 구성한다. admin bypass·부서 합집합 규칙이 한 곳(registry)에 응집되어 있다.
- 👍 주석이 정확하고 의도를 잘 설명한다(경쟁조건 409 처리, iat 기반 토큰 무효화, bcrypt 72바이트 절단 일관성 등 비자명한 결정의 근거가 코드 옆에 명시).
- 👍 함수 길이·파일 길이·중첩 깊이가 모두 기준 내(<50줄/<800줄/<4)이며 네이밍이 도메인 친화적이고 일관적이다.
- **[HIGH]** `backend/app/modules/registry.py:11-63, 89-92` — 권한 진실의 원천이 이중화: 동적 grants 캐시(_GRANTS_CACHE)와 63줄짜리 하드코딩 DEPARTMENT_MODULES가 공존한다. 후자는 '캐시 로딩 전 폴백'이지만, 두 매핑이 시간이 지나면 divergence(예: grants 테이블에 새 부서/모듈이 추가돼도 폴백은 옛 매핑 유지)하고, CLAUDE.md의 '부서/모듈 하드코딩 금지·동적설계' 원칙과 직접 충돌한다. 기동 시 캐시가 비어 폴백이 잡히는 찰나에 잘못된 인가가 나갈 수도 있다.
  - 개선: 폴백을 제거하고 단일 진실의 원천(grants 테이블)으로 통일하라. 기동 시 load_grants_cache()를 lifespan에서 반드시 성공시키고(실패 시 부팅 중단), 시드 데이터(부서 기본 grant)는 마이그레이션/시드 스크립트로 DB에 넣어라. 굳이 폴백이 필요하면 '빈 권한(=dashboard만)'으로 안전하게 닫고 하드코딩 매트릭스는 삭제.
- **[MEDIUM]** `backend/app/routers/users.py:90,106,123,148,186` — user_id로 사용자를 조회 후 None이면 404를 던지는 4~5줄 블록이 approve/reject/reset-password/update/delete 5개 핸들러에 거의 동일하게 복붙되어 있다(DRY 위반). select(User).where(User.id==...) + scalar_one_or_none() + 동일 404 메시지.
  - 개선: '_get_user_or_404(db, user_id) -> User' 헬퍼(또는 FastAPI dependency)를 하나 두고 다섯 곳에서 재사용하라. 404 detail 문자열도 한 곳으로 모인다.
- **[MEDIUM]** `backend/app/schemas/auth.py:25-30, 39-45, 53-58` — _no_whitespace 비밀번호 검증 validator가 RegisterRequest/PasswordChangeRequest/PasswordResetRequest 3개 클래스에 글자 그대로 복붙되어 있다. password 필드 제약(min_length=8,max_length=128)도 함께 반복된다.
  - 개선: Annotated 타입 별칭(예: PasswordStr = Annotated[str, Field(min_length=8,max_length=128), AfterValidator(_no_whitespace)])을 한 번 정의해 세 스키마에서 공유하거나, 공통 베이스 믹스인으로 추출하라.
- **[MEDIUM]** `backend/app/routers/auth.py:28,138-139` — ACCESS_COOKIE_MAX_AGE가 24시간으로 하드코딩되어 있는데 실제 JWT 만료는 config의 access_token_expire_minutes(기본 60분)로 결정된다. 주석은 '24h, matches typical JWT expiry'라고 적혀 있으나 설정과 어긋난다 → 쿠키가 토큰보다 오래 살아 만료된 토큰을 계속 실어 보내는 불일치. 매직넘버 금지 원칙에도 걸린다.
  - 개선: 쿠키 max_age를 settings.access_token_expire_minutes*60에서 파생시켜 단일 출처로 묶어라. 주석도 실제 동작에 맞게 정정.
- **[LOW]** `backend/app/modules/registry.py:100-104` — _user_departments에서 'except Exception: pass'로 모든 예외를 조용히 삼킨다. 코딩 규칙(common/coding-style.md '에러를 절대 조용히 삼키지 말 것')과 충돌하며, lazy-load 외의 실제 버그를 가릴 수 있다.
  - 개선: 기대 예외만 좁게 처리하거나(예: SQLAlchemy DetachedInstanceError), 최소한 logging.warning으로 컨텍스트를 남겨라. lazy='selectin'이 보장된다면 try/except 자체가 불필요할 수 있으니 제거 검토.
- **[LOW]** `backend/app/dependencies.py:36-77` — get_current_user 한 함수가 토큰 추출·디코드·UUID 파싱·DB 로드·is_active/status 게이트·iat vs updated_at 무효화까지 6가지 책임을 직렬로 수행한다(42줄, 기준 내이지만 응집 밀도가 높음). 토큰 무효화 시각 비교 로직은 순수함수로 분리 가능한데 핸들러 안에 인라인되어 단위 테스트가 어렵다.
  - 개선: iat/updated_at 비교를 '_is_token_stale(token_iat, updated_at, grace_sec) -> bool' 순수함수로 추출해 DB·HTTP 의존 없이 단위 테스트가 가능하게 하라. 페이로드→User 매핑과 상태 게이트도 작은 헬퍼로 쪼개면 가독성·테스트성이 함께 오른다.
- **[LOW]** `backend/app/routers/accounts.py:1-17` — accounts 라우터는 require_module(FINANCE) 게이팅을 쓰는 '재무 마스터데이터' 도메인 리소스인데 인증/사용자/권한 모듈 평가 범위에 함께 묶여 있다. 권한 패턴(라우터-레벨 require_module + 핸들러-레벨 require_admin 혼용)은 적절하나, 응집 관점에서 auth 묶음과는 결이 다르다.
  - 개선: 도메인 경계상 finance 묶음으로 보는 게 자연스럽다. 권한 게이팅 패턴 자체는 좋으니 유지하되, 라우터-레벨/핸들러-레벨 의존성 혼용 규칙(생성=member, 수정/삭제=admin)을 모듈 README나 주석 한 곳에 명문화해 일관성을 보장하라.
- **[LOW]** `backend/app/routers/grants.py:45-61` — set_grants가 delete-all-then-reinsert로 부서 grant를 전량 교체한 뒤 load_grants_cache()로 전체 캐시를 재로딩한다. 동작은 맞지만, 단일 부서 변경에 전 테이블 재조회 + 전역 캐시 재구성이라 다중 워커/프로세스 환경에서는 다른 워커의 인메모리 캐시가 갱신되지 않는 일관성 한계가 있다(현재 단일 프로세스 가정).
  - 개선: 현 규모에선 과하지 않으나, 멀티워커로 가면 캐시 무효화를 Postgres LISTEN/NOTIFY나 짧은 TTL 재로딩으로 전파하는 방안을 주석에 가정으로 명시해 두라(YAGNI 범위 내 경고).

## 백엔드: 재무/회계 (transactions / bank_import / matching / counterparts / categories / tax_invoices / balance_snapshots / upload_history / uploads / attachments) — 등급 B  (arch7·simpl6·consist5·read7·modul6·test6)

전반적으로 라우터/서비스/모델 레이어 분리가 명확하고, 어댑터 Protocol + registry 패턴, frozen dataclass DTO, ON CONFLICT chunk insert 등 잘 설계된 부분이 많은 견고한 모듈이다. 그러나 세 벌의 거의 동일한 해시 함수, 두 개의 평행한 엑셀 임포트 파이프라인(신규 bank_import vs 레거시 uploads+excel) 공존, O(n²) 자동매칭, 6개 어댑터 간 대규모 복붙, 그리고 라우터 간 일관성 부족(에러 언어/커밋 책임/응답스키마 위치/경로타입)이 품질을 끌어내린다. 보안/버그가 아닌 순수 장인정신 관점에서 "작동은 견고하나 중복과 평행구조가 누적된" 상태다.

- 👍 은행 어댑터를 Protocol + BaseBankAdapter + registry 로 추상화한 설계가 옳다. 새 은행은 detect/extract_account_meta/extract_transactions 3개만 구현하고 registry 에 한 줄 추가하면 확장된다 — 진정한 plugin 구조이며 동적설계 원칙(하드코딩 금지)에도 부합.
- 👍 DTO 를 모두 frozen=True dataclass(AccountMeta/TransactionDraft 등)로 강제해 어댑터→오케스트레이터→라우터 흐름에서 불변성을 보장. 코딩 룰의 immutability 원칙을 실제로 지킴.
- 👍 서비스 계층이 flush 만 하고 커밋은 라우터가 책임지는 트랜잭션 경계 규약(HIGH-8)을 의도적으로 통일, matching/counterparts 서비스에서 일관 적용. 대용량 임포트를 generator + chunk ON CONFLICT DO NOTHING 으로 처리한 것도 메모리/멱등성 면에서 좋은 선택.
- 👍 account-balances 의 N+1 을 PostgreSQL DISTINCT ON 단일쿼리로 해결, 목록 API 의 X-Total-Count 분리 등 쿼리 설계가 신중하다.
- **[HIGH]** `backend/app/services/bank_import/base_adapter.py / orchestrator.py / routers/transactions.py:base_adapter.py:116, orchestrator.py:50, transactions.py:77` — 거래 해시 SHA256 알고리즘이 세 곳에 거의 동일하게 복제됨(compute_hash=account_number 기반, compute_transaction_hash/_compute_transaction_hash=account_id 기반). 더 나쁜 것은 각 어댑터가 모든 draft 마다 raw_hash 를 계산하는데 orchestrator 가 이를 통째로 버리고 account_id 로 재계산한다(orchestrator.py:362 주석이 'd.raw_hash 는 사용하지 않는다'고 자인). 해시 포맷이 한 곳만 바뀌면 dedup 이 조용히 깨지는 DRY 위반.
  - 개선: 정규 해시 함수를 단 하나(account_id 기반)로 services/bank_import 또는 공용 util 에 두고 transactions.py·orchestrator.py·uploads.py 가 모두 import 하게 통일. 어댑터의 raw_hash 계산 코드와 compute_hash 는 사용처가 없으면 제거(YAGNI). 표시·진단용이 필요하면 명시적으로 그 목적만 남긴다.
- **[HIGH]** `backend/app/routers/uploads.py + backend/app/services/excel.py vs services/bank_import/*:uploads.py:36-138, excel.py:368` — 엑셀 거래 임포트 파이프라인이 두 벌 공존한다. 신규 경로(bank_import: adapter/registry/orchestrator, preview/confirm)와 레거시 경로(uploads.py + excel.parse_bank_excel)가 같은 일(파싱→해시 dedup→insert→UploadLog)을 서로 다른 코드로 수행. 해시 dedup 로직(seen_hashes 루프)과 UploadLog 생성이 uploads.py 안에 다시 인라인되어 라우터에 비즈니스 로직이 샘. 유지보수 시 두 곳을 모두 고쳐야 하고 동작이 갈라질 위험.
  - 개선: 레거시 uploads.py/excel.py 를 신규 bank_import 오케스트레이터로 흡수하거나(라우터는 얇게), 명시적 deprecation 후 제거. 임포트 진입점을 하나로 합쳐 '파싱+dedup+적재'는 서비스에만 두고 라우터는 입력검증/응답매핑만 담당하도록 정리.
- **[MEDIUM]** `backend/app/services/matching.py:38-60` — auto_match_internal_transactions 가 미매칭 거래 전체를 메모리에 적재한 뒤 withdrawals × deposits 이중 루프로 매칭한다(O(n²)). 거래가 누적되면 비용이 급증하고, '같은 금액·날짜±tol'은 본래 인덱스로 set/dict 그룹핑 또는 SQL self-join 으로 풀 수 있는 문제다. 또 첫 일치만 break 하므로 매칭 결정성이 입력 순서에 의존.
  - 개선: (amount, account_id) 키로 deposits 를 dict 인덱싱하거나 date_trunc 윈도우 기반 SQL self-join 으로 후보를 좁힌 뒤 매칭. find_match_candidates 와 동일 불변식을 공유하는 순수 매칭 판정 함수를 분리하면 O(n)·테스트 용이성·결정성을 동시에 확보.
- **[MEDIUM]** `backend/app/services/bank_import/adapters/{kbstar,shinhan,ibk,woori,hana,nonghyup}.py:예: shinhan.py:31-85, kbstar.py:35-90` — 6개 어댑터의 detect()(파일명 hint 체크 + 워크북 상단 키워드 스캔), extract_account_meta 의 '상단 N행 순회하며 계좌번호/예금주 추출' 루프, extract_transactions 의 '계좌번호 선스캔' 루프가 컬럼 인덱스/키워드/행오프셋만 다르고 골격은 거의 동일하게 복붙되어 있다. 새 은행 추가 시 같은 보일러플레이트를 또 복제하게 됨.
  - 개선: BaseBankAdapter 에 detect_by_keywords(keywords, max_row), scan_account_number(max_row), 그리고 컬럼 매핑/헤더키워드/행오프셋을 선언적으로 받는 row→TransactionDraft 변환 템플릿 메서드를 올린다. 어댑터는 '컬럼 스펙' 데이터(deposit_col, withdrawal_col, date_col, header_keywords...)만 선언하도록 줄여 복붙을 제거.
- **[MEDIUM]** `backend/app/routers/transactions.py:1-779` — 파일이 779줄로 800줄 한도에 근접하고 단일 라우터에 list/excel/3종 집계(monthly·top·suggestions)/account-balances/매칭(candidates·match·unmatch)/CRUD(create·update·soft delete·restore)가 모두 들어 응집도가 낮다. 집계 SQL(case/sum/coalesce)이 라우터 함수 본문에 직접 작성되어 비즈니스 로직이 라우터에 샌다(monthly_summary, top_counterparts 등).
  - 개선: 집계 3종은 services/transaction_reports.py 로, 매칭 엔드포인트는 별도 라우터로, CRUD 는 본 파일에 남겨 파일을 기능별로 분할. 집계 쿼리는 순수 함수(입력 필터 → SQL 결과 dataclass)로 빼면 라우터는 호출+직렬화만 하고 테스트도 쉬워진다.
- **[MEDIUM]** `backend/app/routers/{tax_invoices,uploads}.py vs 나머지 라우터:tax_invoices.py:50-56, uploads.py:50, 134` — 라우터 간 일관성 결여: 에러 메시지가 대부분 한국어인데 tax_invoices.py('Account not found' 없음 대신 detail 누락)와 uploads.py('Account not found')는 영어. tax_invoices PATCH 는 detail 없는 빈 404, 응답이 {'status':'linked'} 같은 임시 dict. 일부 라우터는 응답 스키마를 schemas/ 모듈에서, attachments/upload_history/balance_snapshots 는 파일 내부 BaseModel 로 정의. 경로 파라미터도 transactions/attachments 는 str, categories/counterparts 는 uuid.UUID 로 혼재.
  - 개선: 에러 detail 한국어 통일, 경로 파라미터 타입을 uuid.UUID 로 통일(자동 422 검증 이득), 응답 스키마 위치 규약을 하나로(schemas/ 권장) 정하고 tax_invoices 의 placeholder dict 응답을 정식 스키마로 교체.
- **[LOW]** `backend/app/routers/{transactions,attachments}.py:transactions.py:204-217·697-715·728-753·766-779, attachments.py:75-90` — 'select Transaction by id → None 이면 404 → is_deleted 면 410' 패턴이 transactions.py 안에서만 update_memo/update/soft_delete/restore/matching 등 5회 이상 반복되고, attachments.py 는 동일 로직을 _get_transaction 헬퍼로 이미 추출했다. 같은 모듈 안에서 한쪽은 DRY, 한쪽은 복붙으로 갈림.
  - 개선: attachments.py 의 _get_transaction 같은 공용 의존성(get_transaction_or_404, FastAPI Depends 화)을 finance 공용 헬퍼로 올려 transactions 라우터 전반에서 재사용. 404/410 처리 한 곳 수렴.
- **[LOW]** `backend/app/routers/transactions.py / services/bank_import/orchestrator.py:transactions.py:220 (DOWNLOAD_MAX_ROWS), orchestrator.py:193 (max_count=20000), bank_import.py:85 (max_calls=60 주석은 10회)` — 매직넘버·주석 불일치가 산재. _drafts_for_preview 의 max_count=20000 은 confirm 적재 경로에도 그대로 쓰여 2만건 초과분이 조용히 잘릴 수 있다(preview용 한도가 적재에 전용됨). bank_import.py 주석은 '분당 10회'라 하면서 코드는 max_calls=60. transactions.py 의 '최대 깊이 3' 등도 상수화 안 됨.
  - 개선: 한도/윈도우를 모듈 상단 UPPER_SNAKE 상수로 추출하고 preview용·confirm용 한도를 분리(confirm 은 잘림 대신 명시적 거부/경고). 주석과 실제 값 동기화.

## 백엔드: 신사업유통(distribution) — 등급 B  (arch6·simpl6·consist7·read7·modul5·test6)

전반적으로 라우터/서비스/모델 레이어링이 일관되게 지켜지고, 에러처리·권한 가드·응답 형태가 파일 간 통일된 견고한 모듈이다. 다만 생성(generate) 경로의 오케스트레이션 로직 중복(서비스 vs 라우터), 언더스코어 private 함수의 모듈 간 import로 인한 캡슐화 붕괴, 세션 송신 서비스 파일의 비대화(997줄)가 모듈성·테스트 가능성을 끌어내린다. 장인정신은 보이나 DRY와 경계 설계에서 빚이 누적되어 있다.

- 👍 에러 처리·HTTP 상태 매핑·권한 가드(require_module/require_admin)·외부 예외 마스킹 패턴이 9개 라우터 전반에 일관되게 적용되어 있고, 페르소나 단위 실패 격리(try/except 후 errors 누적)로 부분 실패를 견딘다.
- 👍 예약 송신 워커(send_worker.py)의 동시성/재시작 안전 설계가 우수하다 — UPDATE...WHERE send_state='pending' RETURNING 으로 원자적 claim, DB 영속 상태머신, terminal 판정으로 중복 송신을 막는 정공법.
- 👍 다국어(ko/zh) 프롬프트와 BL 라벨을 _BL_LABELS 같은 데이터 테이블로 분기하고, 회사 코드를 DISTRIBUTION_COMPANIES SSOT로 노출하는 등 CLAUDE.md의 '하드코딩 금지·동적 설계' 원칙을 대체로 지킨다.
- 👍 customs_parser의 엑셀/PDF 통합(헤더 후보 매핑 + LLM 1차 → 표 2차 → 정규식 3차 fallback)과 reverse_calc_actual_price의 안전 가드가 깔끔하게 단일화되어 있다.
- **[HIGH]** `backend/app/services/distribution/generation_service.py:376-579` — _create_one_pair_session 과 _create_one_pair_combined_session 이 거의 동일한 본문(발신/수신 role 분기, label_to_id 매핑, DistributionSession 생성, 메시지 루프 저장)을 복붙으로 중복한다. combined 버전이 단일 시나리오도 merge_scenario_contexts(len==1 시 그대로 반환)로 처리 가능하므로 _create_one_pair_session 은 사실상 죽은/잉여 코드에 가깝다. 두 함수의 메시지 저장 루프(564-578)는 글자 단위로 같다.
  - 개선: _create_one_pair_combined_session 하나로 통합하고, 공통 'session+messages 저장' 블록을 _persist_session(db, *, primary, sender, receiver, result, language, group_chat_id) 헬퍼로 추출하라. _create_one_pair_session 은 호출처가 없으면 삭제.
- **[HIGH]** `backend/app/routers/distribution_generate_v2.py:42-49` — 라우터가 generation_service 의 언더스코어 private 함수 5개(_build_bl_context, _create_one_pair_combined_session, _has_credentials, _label_or_id, _top_products)를 직접 import 하고, generate_custom 라우터 핸들러(260-411) 안에 컨텍스트 조회·페르소나/시나리오 선택·세션 생성 루프·커밋/롤백까지 전부 작성한다. 비즈니스 오케스트레이션이 라우터로 새어나왔고(150+줄 핸들러), generate_weekly_for_all_pairs(서비스)와 동일한 흐름이 라우터에 재구현되어 있다.
  - 개선: generation_service 에 공개 함수 generate_custom_sessions(db, *, sender_persona_ids, scenario_names, ad_hoc_instruction, ...) -> GenerationSummary 를 신설해 오케스트레이션을 서비스로 내리고, 라우터는 입력 검증 + 서비스 호출 + 응답 변환만 남겨라. _* 함수의 cross-module import는 공개 API로 승격하거나 서비스 내부로 이동.
- **[HIGH]** `backend/app/routers/distribution.py:222-252` — 레이트리밋 상수(_GEN_PER_MIN_MAX/_GEN_DAILY_MAX/_GEN_DAILY_WINDOW_SEC)와 _enforce_generation_limit 함수가 distribution.py 와 distribution_generate_v2.py 에 글자까지 동일하게 중복 정의되어 있다(DRY 위반). 한 곳에서 한도를 바꾸면 다른 곳이 어긋난다.
  - 개선: app/services/distribution/rate_limit.py (또는 기존 공용 util) 한 곳에 enforce_generation_limit 과 상수를 두고 두 라우터가 import 하라.
- **[MEDIUM]** `backend/app/services/distribution/session_service.py:1-997` — 단일 파일이 997줄로 coding-style의 800줄 한도를 초과한다. 목록/상세 직렬화, 메시지 CRUD·타임라인 편집, 승인/거부/스케줄링, peer/target 해석, 즉시 송신 등 5~6개의 독립 책임이 한 파일에 응집도 낮게 모여 있다.
  - 개선: 최소 'session_query/serialize'(목록·상세·_build_*), 'session_edit'(update/add/delete/manual), 'session_send'(resolve_*, _send_payload, _deliver_message, send_session_now)로 분리하라. send 헬퍼는 워커도 import 하므로 별도 send_core 모듈이 자연스럽다.
- **[MEDIUM]** `backend/app/services/distribution/session_service.py:42-45` — session_service 와 send_worker 가 live_test.py 의 private 함수 _open_telethon_client / _resolve_peer 를, send_worker 가 session_service 의 private _deliver_message 를 import 한다. 'live_test'(CLI 도구로 보이는 모듈)가 운영 송신 경로의 핵심 인프라(telethon client/peer 해석)를 소유하게 되어 의존 방향이 역전됐고, 언더스코어 계약이 모듈 경계를 넘어 깨진다.
  - 개선: telethon client open/peer resolve 를 telethon_login.py 또는 신규 telegram_transport.py 같은 인프라 모듈의 공개 함수로 끌어올리고, live_test·session_service·send_worker 가 그것을 의존하게 하라(의존 방향 정렬 + private 누수 제거).
- **[MEDIUM]** `backend/app/services/distribution/generation_service.py:65-141` — DISTRIBUTION_ACTIVE_ACCOUNT_LABELS = ('VN-A','KR-A1') 라는 계정 라벨 화이트리스트가 서비스 코드에 하드코딩되어 있다. CLAUDE.md의 '계정/브랜드 하드코딩 금지(서울시 고정 금지)' 원칙과 충돌하며, '매칭 0건이면 무시' 폴백 분기까지 더해져 _active_personas_by_role 의 의도를 흐린다(YAGNI성 추측 일반화).
  - 개선: 운영 대상 계정은 persona.active 또는 별도 컬럼/설정(DB·config)으로 표현하고 화이트리스트 상수와 폴백 분기를 제거하라. 활성 여부는 데이터로 제어해 계정 추가 시 코드 변경이 없도록.
- **[LOW]** `backend/app/routers/distribution_sessions.py:100-119` — get_session 핸들러가 'get_session_detail 이 language 를 안 채운다'는 이유로 라우터에서 session.language 를 별도 쿼리해 model_copy 로 재주입한다(주석에 '해당 서비스는 다른 워크스트림 소유라 미수정'이라 명시). 서비스 책임 누수를 라우터 패치로 우회한 것으로, 불필요한 추가 쿼리 + 라우터 비대화를 낳는다.
  - 개선: get_session_detail 의 _build_session_list_item 이 이미 session.language 를 받을 수 있으므로(SessionListItem.language 존재) 서비스에서 한 번에 채우고, 라우터의 재조회/model_copy 분기를 삭제하라.
- **[LOW]** `backend/app/routers/distribution_settlement.py:39-42` — DISTRIBUTION_COMPANIES 를 try/except ImportError 로 감싸고 ('TK101','래더엑스','뉴테인핏','SYBT') 를 인라인 폴백으로 둔다. 같은 SSOT 상수를 다른 라우터(distribution.py/customs.py)는 직접 import 하므로 패턴이 일관되지 않고, 폴백이 SSOT를 분산시켜 회사 추가 시 누락 위험을 만든다.
  - 개선: constants 모듈은 항상 존재하므로 방어적 try/except 와 인라인 폴백 튜플을 제거하고 다른 라우터와 동일하게 직접 import 하라.

## 백엔드: SNS/마케팅 — 등급 C  (arch5·simpl5·consist6·read6·modul5·test5)

수집기(collector) 레이어는 BaseCollector ABC + meta_graph 공용 래퍼로 잘 추상화되어 있고, 내보내기·임포터의 라운드트립 설계와 한국어 에러 변환 일관성은 장인정신이 보인다. 그러나 라우터(sns.py)가 2181줄로 800줄 한도의 약 3배에 달하며, 무거운 SQL 집계·엑셀 피벗·수집 오케스트레이션·LLM 분석이 전부 한 파일에 응집 없이 모여 비즈니스 로직이 라우터로 대량 누수된다. 동일 week_of_month SQL 3중 복붙, LLM 클라이언트 코드 중복, 두 갈래의 LLM 접근 경로 등 DRY/모듈성 부채가 등급을 끌어내린다.

- 👍 수집기 레이어 설계가 견고: BaseCollector ABC가 fetch_posts/followers/metrics/comments 계약을 정의하고, meta_graph.py가 토큰 주입·appsecret_proof·페이지네이션·SSRF 호스트 검증·토큰 마스킹·CollectorError 한국어 변환을 공용화해 facebook/instagram이 깔끔히 공유한다.
- 👍 sns_export.py는 DB를 일절 접근하지 않는 순수 변환 모듈로 설계되어(라우터가 행을 주입) 테스트 용이하고, importer와의 라운드트립 규칙(컬럼 인덱스/헤더 alias)이 양쪽 주석으로 명확히 문서화됐다.
- 👍 동적 설계 원칙 준수: 발주처/채널/어권을 하드코딩하지 않고 DB 계정을 순회하며, 라벨 매핑은 미지의 코드를 원본 그대로 통과시켜 신규 값 추가 시 자동 반영된다.
- 👍 에러 처리 일관성: 외부 API/LLM 실패를 502/503으로, 미지원 플랫폼을 501로, 개별 항목 실패를 격리(failures 누적)하는 패턴이 수집/메트릭/댓글 경로에 일관 적용된다.
- **[HIGH]** `backend/app/routers/sns.py:1-2181` — 단일 라우터 파일이 2181줄로 800줄 한도의 약 3배. 계정 CRUD·게시물·스냅샷·KPI 집계·엑셀 내보내기·ingest·수집 오케스트레이션·메트릭·댓글·LLM 분석/번역·refresh-all·내부 cron·엑셀 임포트 디스패치가 단일 파일에 응집 없이 누적되어 탐색/리뷰/테스트가 모두 어렵다.
  - 개선: 도메인별로 라우터를 분리: routers/sns/{accounts,posts,snapshots,stats,export,collect,comments,ingest}.py + internal.py. 공용 수집 오케스트레이션(_collect_for_account/_collect_metrics_for_account/_refresh_one_account)은 services/sns_service.py(또는 collect_service)로 추출해 라우터는 얇은 HTTP 어댑터로 남긴다.
- **[HIGH]** `backend/app/routers/sns.py:397-490, 568-812, 815-961` — 비즈니스 로직(무거운 SQL 집계·피벗·SimpleNamespace 행 조립)이 라우터 핸들러에 대량 인라인됨. stats_weekly/stats_weekly_posts/export_snapshots/export_workbook가 모두 select·group_by·dict 누적을 직접 수행한다. export_content_status는 라우트 핸들러 stats_weekly_posts를 함수로 직접 호출(db=db 전달)해 레이어 경계를 무너뜨린다.
  - 개선: 집계 쿼리를 services/sns_stats.py(또는 repository)로 옮겨 순수 함수(db, year, month)→rows 형태로 만든다. 라우트끼리 호출하는 대신 공용 집계 함수를 둘 다 호출하게 한다. 이렇게 하면 라우터는 검증·직렬화만 담당하고 집계 로직은 DB 픽스처로 단위 테스트 가능해진다.
- **[MEDIUM]** `backend/app/routers/sns.py:435, 512, 726` — week_of_month 계산식 `func.floor((extract(day)-1)/7).cast(Integer)+1`이 3곳에 동일하게 복붙되고, 그 위 3줄짜리 'SQL 반올림 vs floor' 설명 주석까지 그대로 중복된다(DRY 위반, sns_export._week_of_month의 Python 버전과도 4번째 중복).
  - 개선: 공유 헬퍼 `week_of_month_expr()`(SQL 식 반환)를 services 또는 sns 공용 모듈에 한 번만 정의하고 세 쿼리가 import해 쓴다. 정렬 규칙(floor 기준)을 한 곳에 고정해 향후 불일치 회귀를 차단한다.
- **[MEDIUM]** `backend/app/services/sns_collectors/comment_translator.py:39-98` — comment_translator와 comment_analyzer가 _build_anthropic_client, content 블록에서 text 추출하는 _call_haiku_sync 루프, HAIKU_MODEL 상수, ANTHROPIC_API_KEY 가드를 각자 복붙. 또한 이 두 모듈은 raw `anthropic` SDK를 직접 호출하는 반면, services/translation/translator.py는 services/llm/client.call_claude(Langfuse·캐싱·비용추정 내장)를 쓴다 — 동일 목적의 LLM 접근 경로가 두 갈래로 갈려 비용 추적/캐싱 정책이 한쪽에만 적용된다.
  - 개선: Anthropic 클라이언트 생성·텍스트 블록 추출을 services/llm/ 공용 헬퍼로 통합하고, 댓글 분석/번역도 call_claude 경로로 일원화해 Langfuse 트레이스·prompt caching·비용 추정을 동일하게 받게 한다. 모델 상수도 settings로 끌어올린다.
- **[MEDIUM]** `backend/app/services/sns_collectors/youtube.py:261-283` — _fetch_recent_video_ids가 '혹시 옛 이름을 import하는 호출자 대비' 주석과 함께 남아 있는 사실상 데드코드. _fetch_video_ids(max_pages=1)와 로직이 완전히 중복되며 현재 코드베이스에서 호출되지 않는다(YAGNI 위반).
  - 개선: 사용처가 없음을 grep으로 확인 후 제거. 하위호환이 정말 필요하면 alias = _fetch_video_ids 한 줄로 위임하고 본문 중복을 없앤다.
- **[MEDIUM]** `backend/app/routers/sns.py:815-854` — stats_growth가 활성 계정을 메모리로 로드한 뒤 계정마다 별도 스냅샷 쿼리를 발행하는 N+1 패턴. 계정 수가 늘면 라운드트립이 선형 증가하고, 라우터 안에 집계 로직이 또 인라인된다.
  - 개선: 윈도우 함수(ROW_NUMBER OVER account_id ORDER BY year/month/week desc)로 계정별 최신 2개 스냅샷을 단일 쿼리로 뽑아 services 레이어 함수로 추출한다.
- **[LOW]** `backend/app/routers/sns.py:568-812` — export_snapshots와 export_workbook가 SimpleNamespace로 임시 행 객체를 수동 조립(week1..week5 setattr)하는 패턴이 반복되고, WeeklyPostCountRow를 만든 뒤 다시 SimpleNamespace로 옮겨담는 등(741-770) 변환이 장황하다.
  - 개선: 주차 피벗 결과를 담는 작은 dataclass(또는 기존 WeeklyPostCountRow 재사용)를 정의해 export 빌더와 공유하고, setattr(f"week{n}") 피벗 로직을 헬퍼 한 곳으로 모은다.
- **[LOW]** `backend/app/routers/sns.py:1438-1457, 1619-1632, 2041-2090` — period 검증(`if period not in VALID_PERIODS: 422`)과 '계정 조회 후 404' 패턴이 collect_metrics/collect_comments/refresh_all/internal 핸들러 전반에 반복된다. 동일한 account_or_404 조회 블록도 6곳 이상 복붙.
  - 개선: period를 Literal 타입 또는 공용 Query 검증 의존성으로 끌어올리고, `get_account_or_404(account_id, db)` FastAPI 의존성을 만들어 핸들러 시그니처에서 계정을 주입받게 해 반복 조회/404 분기를 제거한다.

## 백엔드: NAS검색/RAG (routers/nas_search,playground · services/nas_search,playground · schemas/models nas_file) — 등급 B  (arch7·simpl6·consist6·read7·modul6·test7)

NAS 검색 코어(query_embedder / qdrant_search arm / hybrid RRF / reranker)는 레이어링과 책임 분리가 깔끔하고, hybrid.py를 순수함수로 떼어내 테스트 가능성을 의식한 설계가 돋보인다. 다만 search_text 라우터에 점수 게이트·confidence·리랭킹 후처리가 한 함수(120줄)에 응집돼 비즈니스 로직이 라우터로 새고, bridge.py에는 dept 필터·scroll-버킷 패턴이 여러 함수에 복붙돼 있으며, file_walker.py(191줄)는 완전한 dead code로 남아 있다. 전반적으로 견고하나 라우터 비대화·중복·레거시 잔재가 등급을 끌어내린다.

- 👍 hybrid.py를 DB/네트워크 의존 없는 순수 함수(tokenize_query, reciprocal_rank_fusion)로 분리해 단위 테스트가 용이하고, 임베더/리랭커/Qdrant 클라이언트를 일관된 lazy-load 스레드세이프 싱글톤 패턴으로 통일한 점이 장인적이다.
- 👍 qdrant_search의 vector_arm/keyword_arm을 동일한 (order, payload-by-doc_id) 시그니처로 맞춰 RRF 결합부와 깔끔히 분리했고, 점수 게이트·약매칭 강등 같은 검색 품질 결정에 상수 명명과 근거 주석을 충실히 달아 의도가 잘 드러난다.
- 👍 동적 설계 원칙을 잘 지킴: 부서 목록·코퍼스 통계를 Qdrant facet에서 동적 도출(하드코딩 폴더 목록 폐기)하고, 매직넘버 대부분을 settings/모듈 상수로 외부화했다.
- 👍 RAG 통합(nas_rag.py, bridge.search_relevant_chunks)을 검색 모듈과 재사용해 playground와 form_filler가 동일 인프라를 공유 — 중복 검색 스택을 만들지 않은 설계 판단이 옳다.
- **[HIGH]** `backend/app/routers/nas_search.py:300-420` — search_text 핸들러가 120줄에 달하며(함수<50줄 위반), 임베딩→필터빌드→로마자 토큰확장→RRF→confidence 게이트→리랭킹·폴백까지 검색 랭킹 비즈니스 로직 전체가 라우터에 들어있다. 라우터는 HTTP 경계여야 하는데 핵심 도메인 로직이 라우터로 샜다. 이 결정 로직(_keyword_is_strong 게이트, confidence 산출, 리랭킹 후보 선정)은 라우터에 묶여 있어 단위 테스트가 사실상 불가능하다.
  - 개선: 랭킹 파이프라인을 services/nas_search 안의 순수/얇은 함수로 추출하라(예: rank_hits(order_v, by_v, order_k, by_k, *, min_rel, kw_min_match) -> list[ScoredHit], rerank_hits(query, cands)). 라우터는 임베딩·Qdrant 호출 오케스트레이션과 스키마 변환만 남기고, 게이트·confidence·RRF 후처리는 hybrid.py 옆에 두어 hybrid처럼 테스트한다.
- **[HIGH]** `backend/app/services/nas_search/file_walker.py:1-191` — 전체 파일(191줄)이 dead code다. 인앱 인덱싱은 410으로 비활성화됐고(라우터 _indexing_disabled), grep 결과 walk_changed_files/WalkedFile/_collect_candidates를 import하는 곳이 코드베이스 어디에도 없다. NasFile.mtime/size_bytes 비교 로직, 해시 샘플링 등 상당한 코드가 검색 경로와 무관하게 남아 유지보수 혼선을 준다(YAGNI/죽은코드).
  - 개선: file_walker.py를 삭제하라. 동일하게 indexer.py의 IndexProgress도 '항상 idle' 상태 응답만을 위한 잔재이니, /index/status·summary_status 엔드포인트가 정말 프론트 계약상 필요하면 상수 idle 응답으로 축약하고 싱글톤 데이터클래스(reset/finish 미사용 메서드 포함)는 제거한다.
- **[MEDIUM]** `backend/app/services/nas_search/bridge.py:110-114, 175-179, 238-311` — DRY 위반이 반복된다. (1) dept_labels→qm.Filter 빌드 블록이 search_relevant_chunks와 search_per_variable에 글자 그대로 복붙(110-114, 175-179). (2) fetch_chunks_for_files와 fetch_chunks_for_paths는 scroll_filter 키(doc_id vs path)만 다르고 limit 계산·by_X 버킷팅·chunk_index 정렬·per_file_limit 슬라이싱이 거의 동일한 30여 줄 중복. 한쪽 수정 시 다른 쪽 드리프트 위험.
  - 개선: dept 필터는 _dept_filter(dept_labels) -> qm.Filter | None 헬퍼로 추출. fetch 계열은 _scroll_grouped(*, match_key: str, match_values, per_file_limit, group_attr)로 일반화해 doc_id/path 두 함수가 이를 호출하는 얇은 래퍼가 되게 한다.
- **[MEDIUM]** `backend/app/services/nas_search/qdrant_search.py:136-159, 234-264` — _dedup_by_doc_id가 전달받은 payload dict에 pl['_score']를 in-place로 주입하고(_payload_of가 dict(...) 새 사본을 만들긴 하나 의미상 입력 payload 변형), keyword_arm도 동일 payload에 _match_count/_matched_tokens를 in-place 주입한다. 또 '_score'/'_match_count' 같은 언더스코어 키를 payload dict에 섞어 라우터가 pl.get('_score')로 꺼내쓰는 구조라, 도메인 데이터와 내부 메타가 한 dict에 뒤섞여 타입 안전성·가독성이 떨어진다(immutability/명시적 모델 원칙 위반).
  - 개선: arm 반환을 dict 대신 frozen dataclass(예: ArmHit(doc_id, payload, score, matched_tokens))로 바꿔 점수·매칭메타를 payload와 분리하라. 그러면 라우터의 _keyword_is_strong/confidence 로직도 dict.get 매직키 대신 타입드 필드로 다뤄져 더 견고하고 테스트 가능해진다.
- **[MEDIUM]** `backend/app/routers/nas_search.py:437-481` — 다운로드 엔드포인트가 두 개(/files/{id}/download는 nas_files DB 조회 기반, /files/download?path=는 경로 기반)로 갈라져 있는데, 검색 결과는 Qdrant라 nas_files UUID가 없어 전자는 사실상 검색결과로 도달 불가한 레거시 경로다. 같은 '허용 루트 내 검증→FileResponse' 로직이 두 곳에 중복되고 허용 루트도 한쪽은 settings.nas_mount_path, 다른쪽은 하드코딩 튜플 _DOWNLOAD_ROOTS로 불일치한다.
  - 개선: 경로 기반 다운로드 하나로 일원화하고(레거시 ID 기반은 실제 사용처 확인 후 제거), 허용 루트는 settings에 단일 정의해 두 곳이 같은 소스를 참조하게 한다. 검증+FileResponse는 _safe_file_response(path, roots) 헬퍼로 묶는다.
- **[LOW]** `backend/app/routers/playground.py:1-1412` — playground.py가 1412줄로 파일<800줄 기준을 크게 초과한다. 메타·세션·첨부·채팅(SSE)·이미지/영상 task·미디어 서빙·admin 사용량/세션/quota/로그까지 7개 관심사가 한 라우터에 뭉쳐 있고, admin_usage_endpoint 단일 함수도 ~155줄(텍스트/미디어/유저별 4개 집계 + 보강)로 매우 길다. (본 모듈 범위에서는 RAG 주입부 569-619가 핵심이며 그 부분은 깔끔하다.)
  - 개선: 라우터를 도메인별로 분할하라: playground/{chat,sessions,attachments,media,admin}.py + APIRouter include. admin_usage_endpoint의 by_model/by_user 집계는 services/playground/usage_report.py로 추출해 라우터에서 SQL 집계 로직을 빼낸다.
- **[LOW]** `backend/app/services/nas_search/hybrid.py:1-21, 91-98` — 주석/네이밍이 실제 구현과 어긋난다(주석 정확성). 모듈 docstring과 reciprocal_rank_fusion 주석은 '키워드: pg_trgm ILIKE 토큰 매칭', RRF 키를 '파일 경로'라고 설명하지만, 현재 키워드 arm은 Qdrant scroll+substring이고 결합 키는 doc_id다. like_escape()는 ILIKE 전용 헬퍼인데 현행 Qdrant 경로에서 호출처가 없어 보인다(레거시 잔재 가능).
  - 개선: docstring을 Qdrant/doc_id 현실에 맞게 갱신하고, RRF 인자 설명의 '파일 경로'를 'doc_id 등 결합 키'로 정정한다. like_escape의 사용처를 grep으로 확인해 미사용이면 제거(DRY/YAGNI).
- **[LOW]** `backend/app/services/nas_search/qdrant_search.py:55-78, 92-127` — 에러 처리 일관성이 갈린다. corpus_stats는 facet 실패를 내부에서 삼키고 빈 by_dept로 폴백(graceful)하지만, vector_arm/keyword_arm/get_collection 실패는 라우터까지 전파해 502로 만든다. 같은 모듈 안에서 '삼킴 vs 전파' 정책이 함수마다 달라, 호출부가 어디서 무엇이 폴백되는지 추적하기 어렵다.
  - 개선: 폴백 정책을 명시적으로 통일하라: 통계처럼 '부분 실패 허용' 경로와 '검색 실패=502' 경로를 docstring/네이밍으로 구분하고, 삼키는 except는 무엇을 폴백하는지(빈 facet 등) 한 줄로 못박는다. silent swallow가 의도임을 주석으로 분명히.

## 백엔드: 문서작업(docgen) — 등급 B  (arch7·simpl6·consist6·read6·modul6·test6)

docgen/documents/form_filler 서비스 레이어는 순수 함수 분리와 라우터→서비스→모델 레이어링이 대체로 깔끔하고, 출처 레이어(documents/sources.py) 추상화와 가드레일 5방어선 설계는 장인정신이 보인다. 그러나 forms.py가 1350줄로 파일 한도(800)를 크게 초과하며 매핑 영속화·상태전이·source_id 강제 같은 비즈니스 로직이 라우터에 새고, 컨텍스트 빌딩/경로 트래버설 가드/NAS 저장 헬퍼가 여러 곳에 복붙돼 있다. 죽은 코드(LLMResult, JobStatusUpdate, _is_table_line, _EXPLICIT_VAR_HINT_CHARS)와 LLM 클라이언트의 내부 자체 생성(주입 불가)이 단순성·테스트성을 갉아먹는다.

- 👍 서비스 레이어가 순수 동기 함수로 분리되고 라우터가 asyncio.to_thread로 감싸는 패턴이 일관적이라 단위 테스트 친화적이다. generator/mapper/guardrails가 DB·HTTP 의존 없이 입력→출력만 다루어 결합도가 낮다.
- 👍 documents/sources.py의 출처 레이어 추상화가 우수하다 — 엔진(생성/채우기)이 출처(RAG/업로드/both)를 모른 채 NasChunkHit[]만 받게 해 관심사를 깔끔히 분리했다.
- 👍 환각 방어 가드레일(guardrails.py)의 토큰 grounding·경계 일치 숫자 검증, 차트/NAS 저장의 best-effort 폴백 등 엣지 케이스를 의식적으로 방어한 흔적이 견고하다.
- 👍 llm/pricing.py로 단가표를 단일 소스화하고 markdown_blocks 파서를 docx/pptx 빌더가 공유하는 등 의도적 DRY 적용 지점이 분명하다.
- **[HIGH]** `backend/app/routers/forms.py:1-1350` — 파일이 1350줄로 코딩 규칙의 800줄 한도를 크게 초과한다. 16개 엔드포인트 + 임시 Pydantic 스키마(108~243줄) + 상태전이 그래프 + 보조 fetch 함수가 한 파일에 뭉쳐 있다. 응답 스키마는 schemas/form_filler.py가 이미 있는데도 라우터 내부에 중복 임시 정의돼 있다(주석상 'T5-A 머지 후 통일' 부채가 미해소).
  - 개선: 스키마를 schemas/form_filler.py로 이관해 라우터에서 제거하고, 엔드포인트를 도메인별 라우터(templates / jobs / sources / mapping)로 분할한다. _build_job_detail·_fetch_* 보조 함수는 services/form_filler/ 또는 별도 repository 모듈로 내려 라우터를 라우팅+검증만 남긴다.
- **[HIGH]** `backend/app/routers/forms.py:832, 999-1004` — source_id를 UUID로 강제하는 동일한 장황한 인라인 삼항식(`uuid.UUID(m.source_id) if m.source_id and guardrails.is_uuid_like(...) and m.source_id not in {"user_input","web_search"} else None`)이 run_mapping과 regenerate_variable 두 곳에 복붙돼 있다. 한 줄 가독성(>4 중첩 조건)과 DRY를 동시에 위반한다.
  - 개선: guardrails 또는 mapper에 `coerce_source_uuid(value: str|None) -> uuid.UUID|None` 순수 헬퍼를 추가해 sentinel 제외·UUID 검증·변환을 한곳에 캡슐화하고 양쪽에서 호출한다. 테스트도 헬퍼 단위로 작성 가능해진다.
- **[MEDIUM]** `backend/app/services/docgen/generator.py:73-84, 156-170, 240-253` — 참고자료 컨텍스트를 만드는 `ctx = "\n\n".join(f"[참고자료 {i+1}] 출처: {c.file_path}\n{(c.content or '')[:1200]}" ...) else '(검색된 회사 자료 없음...)'` 블록이 generate_document/regenerate_section/review_document 3곳에 거의 동일하게 반복된다. 1200자 컷·빈 자료 안내 문구가 제각각 복제돼 드리프트 위험이 있다.
  - 개선: `_build_context(chunks: list, *, empty_note: str, char_cap: int = 1200) -> str` 단일 헬퍼로 추출하고 3개 함수가 공유한다. 매직넘버 1200도 모듈 상수로 승격한다.
- **[MEDIUM]** `backend/app/services/documents/nas_output.py:69-121` — NAS 사본 저장 + 경로 트래버설 가드 로직이 documents/nas_output.save_to_nas, form_filler/renderer._save_to_nas, forms.py _save_upload_file/_save_template_file/download_job 등 최소 4~5곳에 비슷하게 흩어져 있다. `realpath startswith real_root + os.sep` 경계 검사가 거의 동일하게 복제됐다(응집도 낮음, 한 곳 고치면 나머지 누락 위험).
  - 개선: 경로 정화 + 트래버설 경계 검사를 단일 유틸(예: services/common/safe_path.py의 `assert_within_root` / `safe_write_under`)로 통합하고 모든 저장/다운로드 경로가 이를 경유하게 한다. 이미 better 구현인 nas_output을 기준으로 renderer._save_to_nas를 흡수 통합.
- **[MEDIUM]** `backend/app/services/llm/types.py:16-47` — LLMUsage/LLMResult 데이터클래스가 정의만 되고 어디서도 사용되지 않는다(주석 스스로 '기존 LLMResponse를 대체하지 않는다... 추후 통합 시'라고 명시). YAGNI 위반 — 추측성 일반화로 만든 죽은 추상화다. 동일하게 forms.py:241 JobStatusUpdate, markdown_blocks.py:45 _is_table_line, analyzer.py:27 _EXPLICIT_VAR_HINT_CHARS도 미사용 죽은 코드.
  - 개선: 실제 통합 압력이 생길 때 도입하는 원칙(YAGNI)에 따라 types.py와 위 미사용 심볼들을 제거한다. 통합 계획은 코드가 아니라 백로그/주석으로 남긴다.
- **[MEDIUM]** `backend/app/services/llm/client.py:51-79, 112-113` — call_claude가 매 호출마다 _build_anthropic_client / _build_langfuse_client로 SDK 클라이언트를 내부 생성한다. 의존성이 함수 안에 하드와이어돼 있어 외부에서 가짜 클라이언트를 주입할 방법이 없다 — 단위 테스트 시 모듈 패치(monkeypatch)에 의존해야 하고, 호출마다 클라이언트 재생성 비용도 든다.
  - 개선: 클라이언트 팩토리를 파라미터(기본값=실제 팩토리)로 주입받거나, 모듈 레벨 lazy 싱글톤 + 의존성 주입 시 가능한 Protocol 인터페이스로 추상화한다. 테스트가 SDK 없이 LLMResponse 매핑/비용계산을 검증할 수 있게 된다.
- **[LOW]** `backend/app/routers/docgen.py:292-353` — render와 render_pptx가 빌더 함수(build_docx/build_pptx)와 MIME/확장자만 다를 뿐 본문(try 렌더 → NAS 사본 저장 → quote 파일명 → StreamingResponse)이 거의 완전히 동일하게 중복된다. 동일 응답 형성 로직 2벌.
  - 개선: `_render_and_stream(builder, mime, ext, title, sections, department)` 공용 헬퍼로 추출하고 두 엔드포인트는 빌더/확장자만 넘기게 한다.
- **[LOW]** `backend/app/services/nas_search/bridge.py:89-95` — search_relevant_chunks의 첫 인자 `db=None`이 Qdrant 경로에선 전혀 쓰이지 않는 호환용 vestigial 파라미터다. forms.py는 db를 넘기고 documents/sources.py는 안 넘기는 등 호출 규약이 불일치해 시그니처 의도가 흐릿하다(인지 부하).
  - 개선: 더 이상 pgvector 경로가 없으므로 db 파라미터를 제거하고 모든 호출부를 keyword-only(query=...) 형태로 통일한다. 진짜 제거가 부담되면 최소한 docstring에 'deprecated, 무시됨'을 명시한다.

## 백엔드: 코어 인프라 (config/database/dependencies/main/logging_setup + models + alembic) — 등급 B  (arch7·simpl6·consist5·read7·modul6·test6)

코어 런타임 인프라(database/dependencies/logging_setup)는 장인급으로 잘 짜였다 — get_db의 깔끔한 DI, 기동시 JWT fail-fast, 상수시간 토큰 비교, early-return 인증, 로깅 graceful degradation이 모범적이다. 다만 config.py가 9개 트랙 ~90개 설정을 떠안은 260줄 god-object로 응집도가 무너졌고, 모델 계층은 ID/timestamp 생성 규약이 3가지로 갈리며 models/__init__.py가 4개 클래스를 누락한 stale 상태(autogenerate 잠재 함정)다. 마이그레이션 체인 자체는 선형·단일헤드·전건 downgrade 보유로 깨끗하다.

- 👍 dependencies.py가 인증/인가 횡단 관심사를 깔끔히 분리: get_db(DI), get_current_user, require_admin, require_module(factory), require_internal_token이 단일책임이고 early-return으로 중첩이 얕다. 토큰 추출도 _extract_token 순수함수로 분리돼 테스트 가능.
- 👍 보안 하드닝이 인프라 레벨에서 올바른 위치에 박혀 있다: config의 model_validator로 약한 JWT 기동 차단(B1), secrets.compare_digest 상수시간 비교, database의 pool_pre_ping+pool_recycle로 stale 커넥션 회피(B2), get_db의 예외시 rollback(J2).
- 👍 alembic 마이그레이션이 001~034 선형 체인 + 단일 head + 전 파일 downgrade 보유로 매우 깔끔하고, env.py가 async 엔진+NullPool로 정석 구성. 운영 규약(dev에서 적용/롤백 후 배포)과도 일치.
- 👍 주석이 정확하고 의도(왜)를 설명한다 — config의 게이트 임계값, dependencies의 J1 토큰 무효화 로직, transaction의 H4 오버플로 검증 모두 결정 근거를 남겨 추후 튜닝/유지보수를 돕는다.
- **[HIGH]** `backend/app/config.py:10-243` — 단일 Settings 클래스가 JWT·CORS·NAS검색·Qdrant·리랭커·부서스코핑·form_filler·docgen·Langfuse·Tencent AIGC·playground·distribution·customs 등 9개+ 무관 트랙의 ~90개 설정을 떠안은 260줄 god-object. SRP 위반이고 코어 인프라가 모든 도메인 모듈과 결합된다(한 설정 추가가 코어 파일 수정 유발). 또 nas_rerank_max_length 같은 도메인 튜닝값까지 코어 config에 섞여 응집도가 낮다.
  - 개선: pydantic-settings의 중첩 모델/그룹화로 분해. BaseSettings를 코어(CoreSettings: jwt/cors/db)만 두고, 트랙별 설정은 NasSettings, FormFillerSettings, DistributionSettings, TencentSettings 등 별도 BaseSettings 서브클래스(env_prefix 활용)로 쪼개 settings.nas.min_relevance 형태로 접근. 코어 인프라가 도메인 설정 추가에 영향받지 않게 의존 방향을 끊는다.
- **[HIGH]** `backend/app/models/__init__.py:9, 22-26, 38-71` — SocialPostMetricSnapshot, SocialPostComment(sns.py), PlaygroundAttachment(playground.py), DistributionCustomsDeclaration(distribution.py) 4개 클래스가 정의돼 있으나 __init__의 명시적 import/__all__에서 누락. 현재는 같은 모듈의 다른 클래스를 import하는 side-effect 덕에 Base.metadata에 등록되지만, 누군가 '미사용' import를 정리하면 테이블이 alembic autogenerate에서 조용히 사라지는 잠재 함정. __init__이 모델 레지스트리의 단일 진실원천 역할을 못 한다.
  - 개선: 두 방향 중 하나로 정리: (1) 4개 누락 클래스를 import와 __all__에 추가해 명시적 레지스트리를 완성하거나, (2) __init__을 import-side-effect에 의존하지 않도록 각 모델 모듈을 pkgutil.walk_packages로 자동 import하는 방식으로 바꿔 누락 자체를 구조적으로 방지. 어느 쪽이든 '정의=등록' 보장을 코드로 강제.
- **[MEDIUM]** `backend/app/models/base.py:12-18` — ID/timestamp 생성 규약이 3가지로 분열. (A) UUIDMixin은 python-side default=uuid.uuid4 + updated_at은 onupdate만(최초엔 NULL), (B) distribution.py는 인라인 server_default gen_random_uuid() + updated_at server_default=now(), (C) form_filler/review_translation은 mapped_column default=uuid.uuid4 + server_default+onupdate. ID가 DB-side냐 app-side냐, updated_at이 생성시 NULL이냐 now()냐가 모델마다 달라 dependencies.py의 J1 토큰무효화(updated_at 의존) 같은 횡단 로직이 모델별로 다르게 동작할 위험.
  - 개선: 단일 base 믹스인으로 통일. SQLAlchemy 2.0 Mapped 스타일로 UUIDMixin/TimestampMixin을 재작성(id는 server_default gen_random_uuid로 DB-side 일원화, created_at/updated_at 모두 server_default+onupdate)하고 전 모델이 이를 상속하도록 마이그레이션. 신규 모델이 인라인 Column을 복붙하지 않게 base를 유일 경로로 만든다.
- **[MEDIUM]** `backend/app/main.py:12-43, 92-143` — main.py가 (1) 32개 라우터를 수동 나열 등록, (2) lifespan에서 grant캐시 로드+임베딩 워밍업+리랭커 워밍업+송신워커+미디어정리 5종 백그라운드 작업을 직접 오케스트레이션. 라우터 추가마다 import 블록과 include 블록 2곳 수정 필요(누락 위험), lifespan은 단일 함수에 다종 수명주기가 응집돼 테스트/추론이 어렵다.
  - 개선: 라우터는 각 router 모듈에 APIRouter를 노출하고 routers/__init__.py에 ALL_ROUTERS 리스트를 두어 main에서 for r in ALL_ROUTERS: app.include_router(r) 한 줄로. 백그라운드 수명주기는 startup/shutdown 핸들러 객체(예: BackgroundServices.start()/stop())로 추출해 lifespan을 얇게 유지하면 각 워커 기동조건을 독립적으로 단위테스트 가능.
- **[LOW]** `backend/app/models/playground.py:8-11` — playground.py/distribution.py 주석이 '기존 패턴(account.py/transaction.py)을 따라 Column 스타일로 통일'이라 명시하지만, 실제 코드베이스는 form_filler/review/category/counterpart가 mapped_column(typed) 스타일이라 '통일'이 사실과 다르다. 주석이 현실을 오도하며 신규 작성자가 어떤 스타일을 따라야 할지 혼란.
  - 개선: 프로젝트 차원에서 SQLAlchemy 2.0 Mapped/mapped_column을 표준으로 확정(타입 안전·IDE 지원 우위)하고, '통일' 주석을 실제 표준을 가리키도록 갱신하거나 제거. 점진적으로 legacy Column 모델을 mapped_column으로 마이그레이션.
- **[LOW]** `backend/app/models/distribution.py:34-474` — distribution.py가 473줄로 8개 모델(persona/bl_record/scenario/session/message/weekly_summary/product/send_log/customs)을 한 파일에 담아 800줄 한도엔 미달이나 단일 파일 응집도가 떨어진다. 또 status 문자열('pending/approved/...', 'queued/sent/...')이 enum/상수 없이 server_default 텍스트와 서비스 비교문에 산재(매직 스트링).
  - 개선: distribution 모델을 도메인 하위패키지(models/distribution/persona.py, session.py, customs.py 등)로 분할. status/role 같은 상태값은 modules/constants.py의 UserStatus처럼 str Enum(DistributionSessionStatus, MessageSendState)으로 정의해 모델 server_default와 서비스 비교가 동일 상수를 참조하게 한다.
- **[LOW]** `backend/app/logging_setup.py:27, 48, 61` — 핸들러 중복 부착 방지를 위해 동적 속성 _tk101_name을 핸들러 인스턴스에 monkey-patch(# type: ignore 동반). 동작하지만 표준 logging API(handler.name 또는 get_logger 네임)로 표현 가능한 것을 비표준 속성으로 우회한 형태라 가독성/타입 안정성이 약하다.
  - 개선: logging.Handler.set_name()/get_name()(표준 .name 속성) 사용으로 대체하거나, dictConfig 기반 선언적 로깅 설정으로 전환해 idempotent 부착 체크 자체를 불필요하게 만든다.

## 프론트: 마케팅/대시보드 (pages/marketing, pages/dashboards, components/sns, api/sns.ts) — 등급 B  (arch7·simpl7·consist5·read6·modul6·test5)

전반적으로 견고하고 의도가 분명한 코드다 — API 레이어(api/sns.ts)는 타입·라벨·다운로드 유틸을 한곳에 모아 단일 소스 역할을 잘 하고, 동적 설계(하드코딩 금지) 원칙과 부분 실패 격리(Promise.allSettled) 같은 운영 감각이 곳곳에 살아있다. 다만 페이지/대시보드 레이어에서 일관성이 무너진다: 에러 처리 두 방식 혼재, 라벨맵·포매터·주차 상수의 복붙, 그리고 Marketing1Dashboard가 888줄로 데이터변환·테이블정의·프레젠테이션을 한 컴포넌트에 다 짊어진 점이 가장 큰 부채다. 순수 변환 로직이 컴포넌트 모듈 내부에 묶여 있어 테스트 분리가 어렵다.

- 👍 api/sns.ts가 타입 정의·엔드포인트·라벨맵·옵션·xlsx 다운로드 유틸을 단일 소스로 응집시켜, FollowerTrendChart/AccountSelector/SeoulSns 등이 getPlatformLabel·CONTENT_TYPE_OPTIONS 등을 일관되게 재사용한다. 하드코딩 금지(동적 파생) 원칙도 잘 지켜짐.
- 👍 운영 신뢰성 감각이 좋다: Marketing1Dashboard·DepartmentBaseDashboard가 Promise.allSettled로 위젯별 실패를 격리하고(주석에 회귀 사유까지 기록), refreshAll의 부분 실패를 사용자에게 단계별 message로 안내한다.
- 👍 DepartmentBaseDashboard는 4개 부서 대시보드의 중복을 slot 패턴(extraKpiCards/extraQuickActions)으로 제대로 추상화했고, YAGNI를 의식해 미사용 슬롯에 KISS 주석을 남겼다. AccountSelector도 single/multi 판별 유니온 타입으로 공용 셀렉터를 깔끔히 통합.
- 👍 Marketing1Dashboard의 pivotWeeklyRows/buildTotalRow/aggregateByPlatform 등 변환 함수가 불변(스프레드 복사) 패턴을 일관되게 지켜 사이드이펙트가 없다.
- **[HIGH]** `frontend/src/pages/dashboards/Marketing1Dashboard.tsx:1-888` — 단일 컴포넌트 파일이 888줄로 800줄 한도를 초과한다. 한 파일 안에 (1) 다수 도메인 타입, (2) 6개 순수 변환 함수(pivotWeeklyRows·buildTotalRow·aggregateByPlatform·computeTotals 등), (3) 두 개의 거대한 컬럼 정의, (4) 400줄 가까운 인라인 스타일 JSX가 뒤섞여 있다. 책임이 데이터변환+테이블스키마+프레젠테이션으로 과적재되어 가독성과 변경 안전성이 떨어진다.
  - 개선: 순수 변환 로직(pivot/aggregate/computeTotals/deriveWeekNumbers)을 marketing1/transforms.ts로, 컬럼 빌더를 marketing1/columns.tsx로, 통합요약·플랫폼카드·성장률카드를 각각 프레젠테이션 컴포넌트로 분리. 컴포넌트 본체는 데이터 fetch + 조립만 남겨 300줄 이하로.
- **[HIGH]** `frontend/src/pages/dashboards/Marketing1Dashboard.tsx:79-117` — LANGUAGE_LABELS·PLATFORM_LABELS·LANGUAGE_OPTIONS·PLATFORM_OPTIONS·formatNumber를 로컬에 재정의했는데, 이미 api/sns.ts에 PLATFORM_LABELS/LANGUAGE_LABELS/*_OPTIONS와 getPlatformLabel이 단일 소스로 존재한다. 게다가 라벨이 미묘하게 어긋난다(여기 instagram='인스타', twitter='트위터(X)' vs sns.ts instagram='인스타그램', twitter='트위터'). 같은 화면군에서 플랫폼 표기가 갈리는 DRY 위반 + 표기 드리프트.
  - 개선: sns.ts의 라벨/옵션/포매터를 import해 사용. 표기를 '인스타그램'/'트위터'로 단일화하거나, 정말 대시보드 전용 단축표기가 필요하면 그 사유를 sns.ts에 옵션으로 흡수. formatNumber/formatPercent도 공용 util(numberUtils.ts)로 승격.
- **[MEDIUM]** `frontend/src/pages/marketing/SnsAccounts.tsx:33-38` — 로컬 extractDetail(err)를 직접 정의하고 message.error(detail ? `수집 실패: ${detail}` : '수집 실패') 식으로 에러를 조립한다. 같은 모듈의 SeoulSns·PostMetricsDrawer는 공용 extractErrorDetail(utils/errorUtils.ts)를 쓴다. 한 폴더 안에서 에러 추출/표시 방식이 두 갈래로 갈린다(레포 전체로는 20+ 파일이 로컬 extractDetail 복붙).
  - 개선: SnsAccounts.tsx의 로컬 extractDetail 제거 후 extractErrorDetail로 통일. 메시지도 message.error(extractErrorDetail(err, '수집 실패'))로 일관화. 이 파일을 모범 사례로 삼아 모듈 내 에러처리 패턴을 한 방향으로 수렴.
- **[MEDIUM]** `frontend/src/pages/marketing/SnsContentStatus.tsx:19, 189-205` — 주차 상수 WEEKS=[1..5]와 'week1'..'week5' 키 접근, week별 합산이 SnsContentStatus(5주)·SnsWeeklySnapshots(WEEKS=[1..4])·Marketing1Dashboard(deriveWeekNumbers)에서 제각각 재구현된다. 주차 도메인(최대 주차, week→key 매핑, 주차합산)이 세 곳에 흩어져 변경 시 누락 위험. WEEKS 길이(4 vs 5) 불일치도 잠재 버그.
  - 개선: 주차 도메인을 lib/weeks.ts로 추출: WEEK_NUMBERS 상수, weekKey(n), sumWeeks(rows) 헬퍼. 세 화면이 공유하면 '5주차 달' 처리 로직도 한 곳에서 일관.
- **[MEDIUM]** `frontend/src/pages/dashboards/Marketing1Dashboard.tsx:131-302` — 테스트 가능성: 핵심 비즈니스 로직(가중평균 성장률 aggregateByPlatform, 역산 기반 computeTotals의 prevFollowers = followers/(1+rate))이 컴포넌트 파일에 비-export 로컬 함수로 묶여 있어 단위 테스트로 분리 검증할 수 없다. computeTotals의 성장률 역산은 부동소수 오차에 민감한 비자명 로직이라 특히 검증 가치가 높다.
  - 개선: 변환 함수들을 export된 순수 함수 모듈로 분리(상기 transforms.ts)하고 AAA 패턴 단위테스트 작성. 컴포넌트는 조립만 담당하게 해 vitest로 로직-only 커버리지 확보.
- **[LOW]** `frontend/src/pages/marketing/SeoulSns.tsx:125-152` — fetchPosts가 viewAccountIds 각각에 listPosts를 병렬 호출(N개 계정 → N요청) 후 클라이언트에서 flat/sort/merge한다. 계정 수가 늘면 요청 팬아웃이 커지고 계정별 limit(500)로 잘려 전체 정렬·페이지네이션 정확도가 흔들린다. listPosts가 단일 account_id만 지원하는 API 한계를 프론트에서 우회하는 구조.
  - 개선: 백엔드 listPosts에 account_ids(다중) 또는 기간-전체 조회 파라미터를 추가해 서버에서 정렬·페이지네이션. 단기적으로는 팬아웃 한도/총합 limit를 상수로 명시하고 잘림 가능성을 UI에 표기.
- **[LOW]** `frontend/src/pages/marketing/PostMetricsDrawer.tsx:218-239` — 메트릭 라인차트(6개 Line, 색상/이름 인라인)가 FollowerTrendChart의 recharts 셋업(CartesianGrid·XAxis·YAxis 스타일·SERIES_COLORS·tickFormatter)과 거의 동일한 구성을 중복한다. 차트 스타일 토큰이 두 파일에 흩어져 디자인 시스템 일관성이 코드로 강제되지 않는다.
  - 개선: components/sns에 공통 LineChart 래퍼(축 스타일·그리드·툴팁 포매터·색상 팔레트 주입)를 만들어 두 차트가 공유. coding-style의 '데이터 비주얼라이제이션을 디자인 시스템의 일부로' 가이드에도 부합.
- **[LOW]** `frontend/src/pages/marketing/SnsContentStatus.tsx:198-204` — 합계 컬럼 render가 isTotalRow(row) ? <strong>{fmt(row.total)}</strong> : <strong>{fmt(row.total)}</strong> — 삼항 양쪽이 완전히 동일하다(데드 분기). 의미 없는 분기로 가독성을 해치고 의도(합계만 강조?)가 흐려진다.
  - 개선: 분기를 제거하고 <strong>{fmt(row.total)}</strong> 한 줄로 단순화. 합계행만 다른 스타일을 의도했다면 그 차이를 실제로 반영.

## 프론트엔드: 재무 (finance pages/components/API) — 등급 B  (arch7·simpl6·consist6·read7·modul6·test5)

재무 API 레이어는 도메인별로 잘 분할되고 타입이 명시적이며 주석으로 백엔드 대응을 추적해 전반적으로 장인정신이 보이는 코드다. 다만 Transactions.tsx(1115줄)가 800줄 한도를 크게 넘고, 매칭 후보 fetch/apply 로직이 MatchingWorkbook과 MatchingCandidatesModal에 거의 그대로 복붙되어 있으며, 데이터 페칭이 컴포넌트 내 수동 useState/useEffect로 일관되게 반복되어(서버 상태 라이브러리 부재) 테스트성·DRY가 약하다. 색상 하드코딩과 magic number(7일 윈도우 등)가 디자인토큰/상수로 빠지지 않은 점도 일관성을 떨어뜨린다.

- 👍 API 클라이언트 레이어가 도메인(transactions/accounts/counterparts/categories/uploadHistory/bankImport)별로 깔끔히 분리되고, 모든 export 함수에 명시적 인터페이스·반환 타입이 붙어 있으며 백엔드 라우터 대응을 주석으로 추적해 추후 변경 시 동기화가 쉽다.
- 👍 extractErrorDetail 공용 유틸로 FastAPI {detail} 에러 처리를 단일화하고, isAxiosError로 안전하게 narrowing하는 등 경계 입력 처리가 견고하다. TransactionImport의 중복 confirm 방지(r.result 가드)처럼 실제 버그를 주석과 함께 막아낸 흔적이 있다.
- 👍 Container/Presentational 분리가 부분적으로 잘 지켜진다: MonthlyChart/TopCounterpartsTable/AccountBalanceCard는 props만 받는 순수 표시 컴포넌트로 테스트하기 쉽고, immutable한 setState(맵/필터/스프레드) 패턴을 일관되게 사용한다.
- 👍 TransactionImport의 행 단위 결정(use_existing/create_new/skip) UX와 병렬 미리보기, 부분 실패 집계 등 복잡한 다중 파일 임포트 흐름을 상태기계처럼 정돈해 사용자 친화적으로 처리했다.
- **[HIGH]** `frontend/src/pages/Transactions.tsx:1-1115` — 재무 거래 메인 페이지가 1115줄로 코딩 규칙의 파일 한도(800줄)를 크게 초과한다. 단일 파일 안에 인라인 CategoryCell/MemoCell/BulkCategoryModal/BulkMemoModal 4개 보조 컴포넌트 + 메인 컨테이너 + 20여 개 useState + 십수 개 핸들러가 모두 섞여 응집도가 낮고 변경 영향 범위가 넓다.
  - 개선: 인라인 셀/모달 컴포넌트(CategoryCell, MemoCell, BulkCategoryModal, BulkMemoModal)를 components/finance/ 하위 개별 파일로 추출하고, columns 정의와 필터/URL-state 로직을 별도 훅(useTransactionFilters, useTransactionColumns)으로 분리해 메인 컨테이너를 300~400줄대로 줄인다.
- **[HIGH]** `frontend/src/components/finance/MatchingCandidatesModal.tsx:44-90` — 매칭 후보 조회(getMatchCandidates(id,7))·accountLabel(끝4자리)·applyMatch 성공/실패 처리 로직이 MatchingWorkbook.tsx(110-145)와 거의 동일하게 중복 구현되어 있다(DRY 위반). 두 곳이 ±7일 윈도우, 계좌 라벨 포맷, 매칭 후 메시지까지 평행 진화 중이다.
  - 개선: 후보 조회·적용을 useMatchCandidates(source) 커스텀 훅으로 추출하고, accountLabel/formatAmount 같은 포맷터를 lib/finance.ts 공용 유틸로 모아 두 컴포넌트가 같은 소스를 소비하게 한다.
- **[MEDIUM]** `frontend/src/pages/finance/TransactionImport.tsx:260-310` — handleConfirmAll 내부에서 use_existing/create_new payload를 즉석 조립하며 '미지정','KRW' 등 fallback 문자열과 account_holder 누락 대응이 인라인으로 흩어져 있다. 매직 문자열·결정 분기·중복 가드(confirming, r.result)가 한 함수에 몰려 길이와 분기 깊이가 커진다.
  - 개선: buildConfirmPayload(row): ConfirmPayload 순수 함수로 분리해(테스트 가능) fallback 상수(DEFAULT_BANK_NAME, DEFAULT_HOLDER, DEFAULT_CURRENCY)를 한 곳에 모은다. handleConfirmAll은 오케스트레이션만 담당하게 한다.
- **[MEDIUM]** `frontend/src/pages/finance/MatchingWorkbook.tsx:82-121` — 재무 모듈 전반(MatchingWorkbook, UploadHistory, TransactionImport, Transactions)이 모두 useState+useEffect+try/catch+setLoading 패턴으로 서버 상태를 수동 관리한다. web/patterns.md가 권장하는 서버 상태 분리(TanStack Query/SWR)를 쓰지 않아 로딩/에러/리페치 보일러플레이트가 파일마다 반복되고, 부수효과가 컴포넌트에 묶여 테스트가 어렵다.
  - 개선: 데이터 페칭을 도메인 훅(useUnmatchedTransactions, useUploadHistory 등)으로 감싸거나 TanStack Query를 도입해 캐싱·리페치·에러를 표준화한다. 최소한 'fetch+loading+error' 보일러플레이트를 useAsyncList 같은 공용 훅으로 추출한다.
- **[MEDIUM]** `frontend/src/pages/finance/TransactionImport.tsx:75-82` — extractErrorDetail을 감싸는 동일한 thin wrapper가 MatchingWorkbook(31), UploadHistory(35), TransactionImport(75), 그리고 settings의 Category/Counterpart 페이지에까지 5곳 중복 정의되어 있다. 404 statusMessages 옵션만 다를 뿐 구조가 같다.
  - 개선: errorUtils에 makeErrorExtractor(options) 팩토리 또는 도메인별 프리셋(financeError = (err,fb)=>extractErrorDetail(err,fb,{statusMessages:{404:...},useAxiosMessage:true}))을 export해 각 파일의 wrapper 정의를 제거한다.
- **[MEDIUM]** `frontend/src/components/finance/MonthlyChart.tsx:86-189` — 입금 #52c41a, 출금 #cf1322/#f5222d, 강조 #1677ff 같은 의미색이 finance 전반에 하드코딩되어 같은 의미에 두 가지 빨강(#cf1322 vs #f5222d)이 혼용된다(coding-style의 매직값/하드코딩 금지, web 디자인토큰 권장 위반). 입출금 색·금액 포맷이 컴포넌트마다 재정의된다.
  - 개선: FINANCE_COLORS = { deposit, withdrawal, accent, negative } 상수와 formatKRW/formatAmount/amountColor를 lib/financeFormat.ts로 모아 단일 소스화하고, 빨강 톤을 하나로 통일한다.
- **[LOW]** `frontend/src/components/finance/MatchingCandidatesModal.tsx:58` — 매칭 윈도우 7일이 두 호출부에 매직넘버로 박혀 있고(MatchingWorkbook:114, Modal:58), 카테고리/계좌번호 끝 4자리 슬라이스(slice(-4)), 첨부 10MB(MAX_BYTES) 등 도메인 상수가 파일마다 흩어져 있다.
  - 개선: MATCH_WINDOW_DAYS = 7, ACCOUNT_TAIL_DIGITS = 4 등 도메인 상수를 finance 공용 모듈에 두고 양쪽에서 참조한다.
- **[LOW]** `frontend/src/api/taxInvoices.ts:28-34` — 재무 API 레이어 내 일관성 불일치: transactions/accounts/counterparts/categories는 async/await + res.data 언랩 + 명시 반환타입 패턴인데, taxInvoices.ts와 transactions.ts 일부(downloadExcel, runMatching, getTransactions)는 raw AxiosResponse를 그대로 반환하는 구식 패턴을 섞어 쓴다. 호출부가 .data 처리 방식을 API마다 다르게 알아야 한다.
  - 개선: 전 API를 res.data를 언랩해 반환하는 단일 컨벤션으로 통일하고(blob 다운로드는 별도 명시), @deprecated 별칭(getTransactions, updateMemo)은 호출부 마이그레이션 후 제거한다.

## 프론트: 신사업유통 (distribution) — 등급 C  (arch6·simpl5·consist5·read6·modul4·test5)

기능적으로 잘 동작하고 데이터 페치/에러 처리 패턴은 일관적이며, SessionDetailPage의 컨테이너/프레젠테이션 분리와 중앙화된 extractErrorDetail는 장인정신이 보인다. 그러나 포맷터 헬퍼(formatNumber/Date/Money 등)가 8개 페이지에 복붙되고, 세션 상태 라벨/색상 맵이 3곳에 서로 다른 hex 값으로 중복 정의되며, 회사별 집계 로직이 페이지마다 재구현되는 등 DRY/모듈성 위반이 광범위하다. 3개 파일이 800줄 한도를 초과하고 하드코딩된 회사명("래더엑스") 기본값이 동적설계 원칙을 어긴다.

- 👍 에러 처리가 errorUtils.extractErrorDetail로 단일화되어 모든 페이지/모달이 동일한 FastAPI {detail} 추출 + 사용자 친화 fallback 패턴을 일관되게 사용한다.
- 👍 SessionDetailPage가 TimingEditor/MessageRow/AttachmentBlock/ApproveModal/RejectModal로 책임을 분리한 컨테이너-프레젠테이션 구조라, 1000줄이 넘어도 각 하위 컴포넌트는 작고 응집적이며 테스트 가능하다.
- 👍 타입 규율이 우수하다: any 미사용, 모든 API 함수에 명시적 반환 타입, 백엔드 응답 envelope를 interface로 명시하고 JSDoc로 엔드포인트/비즈니스 규칙(75% 역산, 입금요청 40/30/30)을 정확히 문서화했다.
- 👍 데이터 페치가 useCallback+loading 플래그+Promise.all 병렬 로딩으로 통일되어 있고, 동적 색상 해시(colorForLabel)처럼 브랜드 추가 시 자동 반영되는 동적 설계가 일부 적용됐다.
- **[HIGH]** `frontend/src/api/distribution.ts, distribution_dashboard.ts, pages/distribution/AnalyticsPage.tsx:distribution.ts:635-667, distribution_dashboard.ts:140-156, AnalyticsPage.tsx:102-125` — 세션 상태 라벨/색상 매핑(SESSION_STATUS_LABEL/COLOR)이 최소 3곳에 중복 정의되며 색상 hex가 서로 다르다(예: approved가 distribution.ts는 antd 'blue' 토큰, dashboard.ts는 '#1677ff', Analytics는 '#52c41a'). 동일 상태가 화면마다 다른 색으로 보이는 일관성 결함이자 DRY 위반이다.
  - 개선: 상태→라벨/색상 매핑을 distribution.ts(또는 distribution_constants.ts)에 단일 SSOT로 두고, 대시보드 차트가 antd 토큰 대신 raw hex가 필요하면 토큰→hex 변환 맵 하나만 추가로 둔다. 주석 '의존 방향을 끊기 위해 자체 정의'는 잘못된 합리화 — 상수 import는 순환의존을 만들지 않는다.
- **[HIGH]** `frontend/src/pages/distribution/*.tsx:AnalyticsPage:69-84, DashboardPage:62-75, ProductsPage:77-95, SettlementPage:56-69, CustomsPage:61-75, SessionsPage:60-70, SessionDetailPage:77-95` — formatNumber/formatMoney/formatDate/formatDateTime/formatCost/toIsoDate/ratioPercent 등 순수 포맷터가 7~8개 파일에 거의 동일하게 복붙됐다. 미세한 시그니처 차이(ProductsPage formatNumber는 number-only, Dashboard는 nullable)까지 더해 드리프트가 시작됐다.
  - 개선: frontend/src/utils/format.ts(또는 distribution/format.ts)로 추출해 공유한다. 이 순수 함수들은 추출 즉시 단위 테스트 대상이 되어 testability도 함께 올라간다.
- **[HIGH]** `frontend/src/pages/distribution/ProductsPage.tsx:157-304` — companyStats(157), grandTotal(213), brandStats(268) 세 useMemo가 동일한 'Map 초기화→0 채운 KPI 객체→누적' 패턴을 복붙하고, DashboardPage의 aggregateByCompany(101-150)도 같은 구조다. 7~8개 0 필드 초기화 객체가 4번 반복돼 필드 추가 시 모두 손봐야 한다.
  - 개선: groupSum(rows, keyFn, fields[]) 형태의 제네릭 집계 유틸 하나로 통합하거나, 최소한 emptyKpi() 팩토리로 0 객체 중복을 제거한다. 집계는 순수 함수라 분리 시 테스트도 쉬워진다.
- **[MEDIUM]** `frontend/src/pages/distribution/SessionDetailPage.tsx:1-1070` — 파일 길이 1070줄로 800줄 한도 초과(ProductsPage 930, AnalyticsPage 871도 초과). SessionDetailPage는 TimingEditor/MessageRow/AttachmentBlock/모달 2개 + 페이지 컨테이너가 한 파일에 뭉쳐 있다.
  - 개선: MessageRow/TimingEditor/AttachmentBlock를 components/distribution/session/ 하위로, ApproveModal/RejectModal을 별도 파일로 분리한다. AnalyticsPage의 4개 Tab 컴포넌트도 탭별 파일로 쪼개면 각 파일이 200~300줄로 내려간다.
- **[MEDIUM]** `frontend/src/api/distribution.ts, distribution_generate.ts:distribution.ts:707, distribution_generate.ts:134, CustomsPage.tsx:85, ProductsPage(uploadCompany)` — 회사명 '래더엑스'가 generateWeekly/generateCustom의 기본 company_label과 CustomsPage uploadCompany 초기 state에 하드코딩됐다. CLAUDE.md의 '동적 설계 원칙(브랜드 하드코딩 금지, DB/코퍼스 순회)'에 직접 위배되며, 회사가 추가/변경되면 silent하게 엉뚱한 회사로 적재될 수 있다.
  - 개선: 기본값을 제거하고 호출부에서 명시적으로 company_label을 넘기도록 하거나, DISTRIBUTION_COMPANIES[0] 같은 파생값/사용자 선택값을 강제한다. 업로드 폼은 회사 미선택 시 제출을 막는다.
- **[MEDIUM]** `frontend/src/api/distribution_generate.ts:21, 68, 137 / distribution.ts:16, 576` — DistributionLanguage 타입이 distribution.ts와 distribution_generate.ts 두 곳에 동일 정의되어 있고, 언어 기본값이 모듈마다 불일치한다: distribution.ts 타입 주석·GenerateTriggerModal·generateCustom은 'ko', 그러나 createManualSession·createUserScenario·ManualSessionModal은 'zh'. 같은 도메인에서 기본 언어가 화면마다 달라 사용자 혼란을 유발한다.
  - 개선: DistributionLanguage를 distribution.ts에서 한 번만 export하고 generate 모듈은 import한다. 기본 언어를 단일 상수(DEFAULT_DISTRIBUTION_LANGUAGE)로 정의해 모든 생성 경로가 동일 값을 쓰도록 통일한다.
- **[LOW]** `frontend/src/pages/distribution/ProductsPage.tsx:605-723 / 747-867` — 회사별 요약 카드와 브랜드별 요약 카드가 동일한 'grid 5칸 + 라벨/숫자/색상' 인라인 마크업을 통째로 복붙했다(약 120줄 × 2). 인라인 스타일 객체가 모든 셀에 반복돼 가독성과 재사용성을 떨어뜨린다.
  - 개선: <StatGridCard title qty-items={[{label,value,color}]}/> 같은 프레젠테이션 컴포넌트로 추출하고, web/coding-style.md 권고대로 반복 색상/간격을 CSS 토큰 또는 상수 맵으로 뺀다.
- **[LOW]** `frontend/src/pages/distribution/SessionDetailPage.tsx:329, 121` — 매직넘버: 첨부 크기 한도 200*1024*1024가 인라인으로 박혀 있고(주석/안내문구의 '200MB'와 따로 관리됨), 타이밍 상한 86400도 여러 곳에 반복된다. 한도 변경 시 누락 위험.
  - 개선: MAX_ATTACHMENT_BYTES, MAX_SEND_AFTER_SEC 등 명명 상수로 추출하고 안내 문구도 그 상수에서 파생시킨다(coding-style.md 매직넘버 금지).

## 프론트엔드: 문서/폼/NAS/플레이그라운드 (frontend/src/pages/{documents,forms,nas,playground}, components/{forms,playground}, 관련 api) — 등급 B  (arch7·simpl6·consist5·read7·modul5·test5)

전반적으로 잘 정돈된 React+antd 프론트엔드다. NAS 검색은 컴포넌트 분해(SearchResults/ResultSummaryBar/EmptySearchHelp)와 순수 유틸 분리(nasUtils)가 모범적이고, usePlaygroundChat 훅은 스트리밍 상태를 깔끔히 캡슐화했다. 다만 모듈 전반에 일관성 결함이 누적돼 있다: blob 다운로드 로직이 7곳 복붙, 이미 존재하는 공용 에러 추출 유틸(extractErrorDetail)을 두고도 4개 파일이 손으로 response?.data?.detail를 재구현, MediaGenPanel은 849줄로 단일 파일 한계에 근접한다. fileIconType 호출부 인자 불일치로 검색 요약 바가 실제 결과와 다른 파일종류 통계를 보여주는 품질 버그도 존재한다.

- 👍 NAS Search.tsx의 컴포넌트 분해와 phase 상태머신(idle/searching/done)이 명료하고, 순수 함수(summarizeMime, fileIconType, formatFileSize)를 nasUtils로 분리해 단위테스트(nasUtils.test.ts)까지 갖춘 점이 모범적이다.
- 👍 usePlaygroundChat 훅이 세션 생성/스트리밍/누적 usage/abort를 한 곳에 캡슐화하고 불변 업데이트(map/spread)를 일관되게 지켜, 패널 컴포넌트가 표현에 집중할 수 있게 한다.
- 👍 MappingTable의 ValueCell이 로컬 draft로 키 입력을 흡수하고 blur/Enter에만 커밋하는 패턴, LlmChatPanel의 STATIC_PROVIDERS 폴백 등 사용자 경험·견고성을 위한 의도적 설계가 보인다.
- 👍 주석이 '왜'를 설명(예: Decimal→string 직렬화, mtimeFrom 필터 의도)하고 대체로 코드와 일치해 가독성이 높다.
- **[HIGH]** `frontend/src/api/docgen.ts, frontend/src/api/nas.ts, frontend/src/api/forms.ts, frontend/src/components/playground/MediaGenPanel.tsx, frontend/src/api/sns.ts, frontend/src/components/playground/SessionList.tsx:docgen.ts:99-106, 122-129; nas.ts:111-118; MediaGenPanel.tsx:583-591, 607-614` — blob을 받아 <a download>를 만들고 클릭→revoke하는 동일 다운로드 로직이 최소 7곳에 복붙되어 있다(DRY 위반). createObjectURL/createElement('a')/appendChild/click/remove/revokeObjectURL 6줄 시퀀스가 파일마다 미세하게 다르게 반복돼 드리프트(어떤 곳은 removeChild, 어떤 곳은 a.remove())가 이미 발생.
  - 개선: utils/download.ts에 triggerBlobDownload(blob, filename) 단일 함수를 만들어 모든 호출부를 교체. MediaGenPanel의 mediaId 우선 fetch→텐센트 fallback도 fetchBlob(url, opts) 헬퍼로 추출하면 같은 try/catch 블록 중복(MediaGenPanel.tsx 576-618)도 제거된다.
- **[HIGH]** `frontend/src/pages/nas/Search.tsx:222` — summarizeMime가 fileIconType(hit.mime_type, hit.file_type)를 호출하며 name(파일명)을 넘기지 않는다. 그런데 fileIconType의 1차 판별은 확장자 기반이고 Qdrant 결과는 mime_type이 null인 경우가 많아, 결과 요약 바의 종류 통계가 대부분 '기타(file)'로 뭉개진다. 반면 NasResultItem.tsx:23은 name까지 넘겨 정확히 분류 → 같은 데이터에 대해 요약 바와 리스트가 서로 다른 분류를 보여준다.
  - 개선: summarizeMime에서 fileIconType(hit.mime_type, hit.file_type, hit.name)로 name을 전달. 호출부 인자 누락을 컴파일 단에서 막으려면 fileIconType의 name을 선택 인자가 아닌 필수로 올리거나, NasSearchHit를 받는 래퍼 fileKindOfHit(hit)를 만들어 호출 표면을 단일화한다.
- **[MEDIUM]** `frontend/src/components/playground/MediaGenPanel.tsx:1-849` — 한 파일에 MediaGenPanel(폼/폴링/제출)·TaskCard·I2VModal·downloadTaskOutput·날짜 그룹핑 유틸까지 849줄로 응집돼 있다. 800줄 가이드라인 상한을 사실상 초과했고, 폴링 로직(startPolling)과 i2v 제출 핸들러가 한 컴포넌트에 묶여 응집도가 떨어진다.
  - 개선: TaskCard/I2VModal을 별도 파일로, 날짜 그룹핑(groupTasksByDate/toDateKey/dateGroupLabel)을 mediaUtils.ts로 분리. 폴링은 usePolling(taskId, fetcher) 또는 useMediaTasks 훅으로 추출하면 본체가 ~300줄로 줄고 폴링 로직이 단위테스트 가능해진다.
- **[MEDIUM]** `frontend/src/components/playground/MediaGenPanel.tsx, frontend/src/pages/forms/JobMappingPage.tsx, frontend/src/components/playground/SessionList.tsx, frontend/src/pages/forms/FormUploadPage.tsx:MediaGenPanel.tsx:373-377; JobMappingPage.tsx:134-136` — utils/errorUtils.ts에 공용 extractErrorDetail(err, fallback, {statusMessages})가 이미 존재하는데, 이 4개 파일은 (err as {response?:{data?:{detail?:string}}})... 형태로 detail을 손으로 캐스팅·추출한다. 에러 처리 형태가 모듈마다 제각각이고 any-ish 캐스팅이 타입 안전성을 깬다.
  - 개선: 해당 catch 블록들을 extractErrorDetail(err, '...')로 교체. 동시에 다수 핸들러가 message.error('~ 실패')만 하고 err를 통째로 버리는데(예: DocGenPage handleGenerate), 최소한 extractErrorDetail로 백엔드 detail을 노출해 사용자 피드백 품질을 통일한다.
- **[MEDIUM]** `frontend/src/pages/forms/JobMappingPage.tsx:83-89, 296-299` — '매핑이 없거나 value가 null/공란이면 누락'이라는 동일한 필터 술어가 JobMappingPage의 missingMappings(83-89)와 MissingFormModal 내부(296-299)에 그대로 두 번 작성됐다. 누락 판정 규칙이 바뀌면 두 곳을 동시에 고쳐야 하는 drift 위험.
  - 개선: isMissing(variable, mappings) 또는 selectMissingVariables(detail) 순수 함수를 forms 유틸로 추출해 양쪽에서 재사용. JobMappingPage 양식 미리보기의 filled 판정(221)도 같은 규칙이므로 함께 통일한다.
- **[MEDIUM]** `frontend/src/pages/forms/DocGenPage.tsx:55-250` — DocGenPage가 12개 useState로 생성·편집·재생성·검수·자동보강 상태를 한 컴포넌트에서 모두 관리한다(475줄). handleAutoFixAll/regenerateFromReview/buildReviewFeedback 등 비즈니스 로직(검수 피드백→재생성 매핑, 순차 보강 루프)이 프레젠테이션과 한 파일에 섞여 있어 테스트가 어렵다.
  - 개선: 초안 상태(title/sections/feedbacks/regen)와 검수/자동보강 상태를 useDocDraft, useDocReview 두 훅으로 분리. buildReviewFeedback·findSectionIndex 같은 순수 변환은 docgenUtils로 빼면 컴포넌트가 얇아지고 핵심 로직을 vitest로 직접 검증할 수 있다.
- **[LOW]** `frontend/src/components/playground/MediaGenPanel.tsx, frontend/src/api/docgen.ts:MediaGenPanel.tsx:291,299-301; docgen.ts:43` — 기본 aspect_ratio '1:1'/'16:9', resolution '720P', duration 5, limit 8 등 도메인 기본값이 onSubmit 본문과 API 함수에 매직 문자열/숫자로 흩어져 있다. 같은 기본값이 폼 initialValues와 onSubmit fallback 양쪽에 중복 하드코딩돼 둘이 어긋날 수 있다.
  - 개선: DEFAULT_IMAGE_FORM/DEFAULT_VIDEO_FORM 상수 객체를 한 곳에 정의해 initialValues와 onSubmit fallback이 같은 소스를 참조하게 한다. ASPECT_RATIO_OPTIONS처럼 이미 상수화된 패턴과 일관되게.
- **[LOW]** `frontend/src/components/playground/LlmChatPanel.tsx:139-165, 199-207` — refreshKey 증가용 상태가 sessionListKey/quotaRefreshKey 두 개에, prevSending·lastSeenSessionId·shownQuotaError 등 '이전 값 추적' useEffect가 여러 개 쌓여 있다. 'prop이 바뀌면 카운터를 올려 자식 재조회'라는 우회 패턴이 반복돼 데이터 흐름이 추적하기 어렵다(서버 상태를 클라이언트로 복제하지 말라는 web/patterns 권고와도 상충).
  - 개선: refreshKey 트릭 대신 TanStack Query 같은 서버 상태 라이브러리의 invalidate, 또는 자식이 직접 구독하는 콜백/이벤트로 단순화. 최소한 bumpXxx 패턴을 useRefreshKey() 훅으로 묶어 보일러플레이트를 줄인다.

## 프론트 코어 (라우팅/공통/API) — 등급 C  (arch6·simpl5·consist4·read6·modul5·test4)

코어의 설정 레이어(config/modules.tsx)는 동적·순수·문서화가 잘 된 모범 사례이고 인증 게이트/ProtectedRoute 추출도 깔끔하다. 그러나 App.tsx는 38개의 거의 동일한 라우트 블록을 손으로 유지하며 NAV_ITEMS와 별개의 두 번째 진실원천을 만들고, API 레이어는 res.data 언랩 방식과 raw axios 반환 방식이 혼재하며, 동일한 extractErrorDetail 래퍼(스테일한 "Wave 5" 하드코딩 문자열 포함)가 5개 파일에 복붙되어 일관성·DRY·테스트 용이성이 함께 떨어진다. 설계 골격은 건전하나 장인정신 측면의 마감이 부족하다.

- 👍 config/modules.tsx의 buildSidebarMenuItems는 순수함수 + 설정주도 + 카테고리 order/빈그룹 숨김까지 처리하고 주석으로 '부서 추가 시 양쪽 등록' 의도를 명시 — 동적설계 원칙(하드코딩 금지)을 정확히 따른 모범 사례
- 👍 ProtectedRoute / AppLayout / useAuth로 라우팅·레이아웃·인증 관심사가 깔끔히 분리되어 있고, App.tsx의 user 유무 기반 라우트 분기(로그인 게이트)가 명료
- 👍 errorUtils.ts를 공통 유틸로 추출하고 vitest 단위테스트(AAA 패턴, 엣지케이스 5개)까지 갖춤 — 순수함수 테스트의 좋은 예
- 👍 코어 파일들(App/client/modules/layout)은 800줄 제한과 중첩 깊이 규칙을 대체로 준수
- **[HIGH]** `frontend/src/App.tsx:84-391` — 38개의 거의 동일한 <Route><ProtectedRoute user={user} module="...">…</ProtectedRoute></Route> 블록이 손으로 반복된다. path↔module 매핑은 이미 config/modules.tsx의 NAV_ITEMS에 존재하는데(36개), 라우트는 별도로 유지되어 두 번째 진실원천이 생기고 드리프트(라우트 38 vs 네비 36)가 발생한다. DRY 위반 + 라우트/네비 동기화가 수동.
  - 개선: 라우트를 데이터 주도로 전환: {path, element, module}[] 배열(또는 NAV_ITEMS 확장)을 .map()으로 렌더하고 ProtectedRoute로 감싸는 작은 래퍼/HOC를 도입. NAV_ITEMS와 라우트가 동일 소스에서 파생되도록 해 path/module 매핑을 단일화.
- **[HIGH]** `frontend/src/pages/settings/CategoryPage.tsx:38-46 (+ CounterpartPage:45, finance/TransactionImport:78, finance/UploadHistory:38)` — 공통 extractErrorDetail 유틸이 있음에도 각 페이지가 동일한 로컬 래퍼를 복붙하고, 그 안에 '백엔드 라우터가 아직 등록되지 않았습니다 (Wave 5 예정).'라는 스테일한 매직 문자열이 5곳에 하드코딩되어 사용자에게 그대로 노출된다. DRY 위반 + 내부 개발 컨텍스트가 프로덕션 메시지로 유출.
  - 개선: 재무 모듈 공용 에러 매핑(statusMessages 프리셋)을 errorUtils 또는 api/finance 공통 모듈에 한 번만 정의하고 import. 'Wave 5' 같은 임시 문구는 일반적인 404 메시지로 교체.
- **[HIGH]** `frontend/src/api/auth.ts:28-36 (vs api/categories.ts:40, api/transactions.ts:143)` — API 레이어에 두 가지 반환 컨벤션이 공존한다. auth/nas/sns 모듈은 raw AxiosResponse를 반환(호출부가 res.data를 풀어야 함)하고, categories/counterparts/accounts/transactions는 async 함수로 res.data를 언랩해 반환한다. 호출부가 모듈마다 어느 방식인지 알아야 하며, 공통 응답 엔벌로프도 없다.
  - 개선: 한 가지 컨벤션으로 통일(권장: 항상 res.data를 언랩한 도메인 타입 반환). 페이지네이션 등은 typescript/patterns의 ApiResponse<T> 엔벌로프 채택 검토. 리팩토링을 모듈 단위로 점진 적용.
- **[MEDIUM]** `frontend/src/pages/settings/CounterpartPage.tsx:67-227` — CounterpartPage와 CategoryPage가 동일한 CRUD 스캐폴딩(fetch+loading+modal open/edit 상태머신, create/edit 분기 submit, message.success/error 패턴)을 거의 그대로 중복한다. 데이터 로딩·에러매핑·렌더가 한 컴포넌트에 융합되어 있어 컨테이너/프레젠테이션 분리가 없고, 의존성 주입이 불가능해 단위 테스트가 어렵다.
  - 개선: 공통 리스트/CRUD 로직을 useCrudResource 같은 커스텀 훅 또는 컨테이너 컴포넌트로 추출(server state는 TanStack Query 도입 검토). 폼 모달 스캐폴딩도 재사용 컴포넌트로. 이렇게 하면 순수 프레젠테이션 컴포넌트는 props만으로 테스트 가능.
- **[MEDIUM]** `frontend/src/api/client.ts:10-27` — API 클라이언트가 401 응답에서 직접 window.location.href='/login'으로 하드 리다이렉트하고 localStorage 토큰을 지운다. API 레이어가 라우팅/네비게이션 관심사에 결합되고, 테스트 시 전역 부수효과(전체 페이지 이동)를 유발해 모킹이 어렵다. 또한 localStorage 토큰과 httpOnly 쿠키 이중 인증 모델이 client/useAuth/App에 분산.
  - 개선: 401 처리를 이벤트/콜백(예: onUnauthorized 핸들러 주입)으로 위임하거나 라우터 가드에서 처리해 API 레이어를 순수하게 유지. 인증 토큰 소스를 단일화하고 그 정책을 한 곳(useAuth)에 모을 것.
- **[MEDIUM]** `frontend/src/pages/settings/CategoryPage.tsx:55-69` — nodeDepth가 root를 두 번 순회한다(먼저 1depth 매칭 루프, 이후 별도 재귀 findDepth). 재귀 findDepth 하나로 충분하므로 죽은/중복 로직이며 의도가 흐려진다. 또한 depth<3 제한의 '3'이 canAddChild에 매직넘버로 박혀 있다(설명 주석은 있으나 상수화 안 됨).
  - 개선: nodeDepth를 단일 재귀로 단순화하고, MAX_CATEGORY_DEPTH 상수를 도입해 canAddChild와 안내 문구가 같은 상수를 참조하도록.
- **[LOW]** `frontend/src/components/AppLayout.tsx:37-147` — 레이아웃이 대량의 인라인 style 객체(다크모드 그림자, 사이드바 색/패딩, 0.05em letterSpacing 등)와 rgba 하드코딩 색을 직접 들고 있다. web/coding-style의 디자인 토큰(CSS 변수)·매직값 금지 가이드와 어긋나고, 동일 색/간격이 여러 곳에 반복된다.
  - 개선: 반복되는 색/간격/그림자를 디자인 토큰(antd theme token 또는 CSS 변수)으로 추출하고, 인라인 style 덩어리는 styled/className으로 분리해 가독성과 일관성 확보.
- **[LOW]** `frontend/src/App.tsx:58-63` — 다크모드 부수효과(localStorage 쓰기 + document.documentElement/body 직접 스타일 변경)가 최상위 App 컴포넌트에 박혀 있다. 테마 관심사가 App에 누수되어 재사용·테스트가 어렵고, DARK_MODE_KEY 외 '#000'/'#f5f5f5' 배경값이 매직 상수.
  - 개선: useDarkMode 커스텀 훅으로 상태+persist+DOM 부수효과를 캡슐화하고, 배경색을 토큰/상수로 분리. App은 훅이 주는 값만 소비.