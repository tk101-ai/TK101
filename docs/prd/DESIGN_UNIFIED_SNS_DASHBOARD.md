# 통합 SNS 대시보드 설계 (마케팅1팀)

> READ-ONLY 조사 기반 설계 문서. 코드 변경 없음.
> 대상 저장소: `/home/ubuntu/tk101-dev` (FastAPI + React/TS + Ant Design)
> 작성일: 2026-06-22

---

## 0. 한 줄 요약

YouTube / Facebook / Instagram이 이미 DB·수집기·API 레벨에서 **통합되어 있다.**
흩어져 보이는 것은 **프론트엔드가 5개 화면(`/sns/*`)으로 쪼개져 있고**, 수집(갱신)이
**n8n 크론에만 묶여 사용자가 직접 누를 버튼이 없으며**, 계정 **삭제(DELETE) 엔드포인트가
없고**, 대시보드 **트렌드 차트가 placeholder("준비 중")** 인 탓이다. 따라서 이 작업은
"새 시스템 구축"이 아니라 **기존 자산 위에 (1) 통합 대시보드 1페이지, (2) 전체 갱신 버튼,
(3) 계정 DELETE + 동적 셀렉터, (4) 트렌드 차트, (5) 사용자별 뷰 저장**을 얹는 것이다.

---

## 1. 현재 상태 (조사 결과, file:line)

### 1.1 데이터 모델 — 이미 플랫폼 통합 (`backend/app/models/sns.py`)

| 모델 | 테이블 | 핵심 컬럼 |
|---|---|---|
| `SocialAccount` (L19) | `social_accounts` | `platform`, `language`, `handle`, `page_url`, `external_id`, `is_active`, `client`, `extra_metadata(JSONB)` |
| `SocialWeeklySnapshot` (L33) | `social_weekly_snapshots` | `account_id`, `year`, `month`, `week_number(1-5)`, `followers`, `captured_at` — **팔로워 추이의 기존 기반** |
| `SocialPost` (L44) | `social_posts` | `account_id`, `posted_at`, `title`, `content_type`, `producer`, `view_count`, `reach_count`, `comment_count`, `like_count`, `share_count`, `total_engagement`, `url`, `external_id`, `is_manual`, `extra_metadata` |
| `SocialPostMetricSnapshot` (L68) | `social_post_metric_snapshots` | `post_id`, `period('daily'|'weekly')`, `views`, `reach`, `likes`, `comments`, `shares`, `engagement_total`, `raw` — **게시물 메트릭 시계열** |
| `SocialPostComment` (L94) | `social_post_comments` | 댓글 본문 + 한국어 번역 캐시 |

핵심: **모든 플랫폼이 같은 4개 테이블을 공유**한다. 플랫폼 구분은 `social_accounts.platform`
한 컬럼이고, 게시물·스냅샷은 `account_id` FK로만 연결된다. "통합"은 데이터 레벨에서 이미 끝나 있다.

### 1.2 계정 저장 방식 — 하드코딩 아님, DB 행

- 마이그레이션 003/022는 **스키마만 생성**, INSERT 시드 **없음** (`022_sns_meta_channels.py` 확인).
- 계정 행이 생기는 경로는 둘:
  1. **관리자 API** `POST /api/sns/accounts` (`routers/sns.py:86`, `require_admin`).
  2. **엑셀 임포트** `_ensure_accounts()` (`sns_importers/marketing1.py:408`) — `(platform, language)`
     키로 멱등 생성.
- 즉 "3개 계정"은 하드코딩이 아니라 **현재 DB에 3행만 있는 상태**다. 셀렉터가 고정처럼 보이는 건
  프론트가 `listAccounts()` 결과를 그대로 쓰되 **화면마다 셀렉터를 따로 구현**하기 때문.

### 1.3 데이터 갱신(refresh) 방식 — 오늘은 n8n 크론 전용

| 트리거 | 엔드포인트 | 대상 | 스케줄 (n8n) |
|---|---|---|---|
| 단일 계정 수동 | `POST /api/sns/collect/{account_id}` (`sns.py:657`, admin) | youtube/facebook/instagram | SnsAccounts "수집" 버튼 |
| **전체 수집** | `POST /api/internal/sns/collect-all` (`sns.py:1302`) | `SUPPORTED_PLATFORMS` 활성 계정 | `youtube_daily.json` 월 05:00 KST |
| 메트릭 일/주 | `POST /api/internal/sns/collect-metrics-all?period=` (`sns.py:1346`) | `METRICS_PLATFORMS`=(fb,ig) | `sns_meta_metrics_daily/weekly.json` |
| 댓글 전체 | `POST /api/internal/sns/collect-comments-all` (`sns.py:1398`) | (fb,ig) | (n8n 워크플로 아직 없음) |

- 내부 라우터는 `X-Internal-Token`(`settings.internal_api_token`) 인증.
- `collect-all`은 **개별 계정 실패를 격리**(L1330 `except HTTPException` → `failures` 누적)하고,
  전부 실패할 때만 502를 던진다. → **전체 갱신 버튼의 부분 실패 처리 패턴이 이미 존재한다.**
- 동기(대화형) 호출은 nginx 60s 회피용 상한(`METRICS_MAX_POSTS_PER_RUN=20`, `_QUICK_MAX_PAGES=2`)이
  걸려 있고, 전체 백필은 크론(`max_posts=None`, `full=True`)이 담당.

### 1.4 메트릭/수집기 (`services/sns_collectors/`)

| 플랫폼 | 토큰 (env) | followers | posts | post-metrics | comments |
|---|---|---|---|---|---|
| YouTube (`youtube.py:75`) | `GOOGLE_YOUTUBE_API_KEY` | ✅ 구독자(`/channels`) | ✅ 조회/좋아요/댓글 | ❌ (API 미지원) | ❌ |
| Facebook (`facebook.py:82`) | `META_ACCESS_TOKEN` | ✅ `followers_count` | ✅ 좋아요/댓글/공유/도달 | ✅ `/insights` | ✅ |
| Instagram (`instagram.py:81`) | `META_ACCESS_TOKEN` | ✅ `followers_count` | ✅ media | ✅ reach/views/likes/comments | ✅ |

- Meta 공통 클라이언트 `meta_graph.py`: `appsecret_proof` HMAC 서명, `graph_get_paged`(최대 50p),
  토큰 없으면 한국어 `CollectorError` → 503.
- YouTube는 단일 게시물 메트릭/댓글 시계열 미지원 → **트렌드는 채널 단위(구독자)만, 게시물 단위는 Meta만.**

### 1.5 통계/위젯 엔드포인트 (`routers/sns.py`)

| 메서드+경로 | 용도 |
|---|---|
| `GET /api/sns/accounts` (L68) | 계정 목록 (platform/language/is_active 필터) |
| `POST /api/sns/accounts` (L86, admin) | 계정 생성 |
| `PATCH /api/sns/accounts/{id}` (L100, admin) | 계정 수정 (소프트삭제 = `is_active=false`) |
| `GET /api/sns/meta/whoami` (L120, admin) | Meta 토큰 진단 |
| `GET /api/sns/posts` (L158) | 게시물 목록 (account/date/type/lang/platform 필터) |
| `GET /api/sns/snapshots` (L236) | 주간 팔로워 스냅샷 |
| `GET /api/sns/stats/weekly` (L281) | 어권×플랫폼×주차 KPI 테이블 |
| `GET /api/sns/stats/growth` (L374) | 채널별 최신 vs 직전 스냅샷 성장률 |
| `GET /api/sns/stats/top-posts` (L414) | 인기 콘텐츠 Top N |
| `GET /api/sns/stats/trend` (L456) | **빈 배열 반환 placeholder** ← 트렌드 미구현 |
| `POST /api/sns/collect/{id}` (L657, admin) | 단일 수집 |
| `POST /api/sns/accounts/{id}/collect-metrics` (L925) | 게시물 메트릭 수집 |
| `GET /api/sns/posts/{id}/metrics` (L948) | 게시물 메트릭 시계열 |
| `DELETE /api/sns/accounts/{id}/posts` (L1271, admin) | 콘텐츠만 삭제 (계정 보존) |
| 내부 `collect-all` / `collect-metrics-all` / `collect-comments-all` | 일괄 수집 |

**없는 것:** 계정 자체 `DELETE`, 전체 갱신용 **공개(비-internal) 트리거**, 트렌드 데이터.

### 1.6 프론트엔드 — 흩어진 5개 화면 (`frontend/src`)

라우팅 `App.tsx:158-196`, 메뉴 `config/modules.tsx:102-106` (모두 `marketing_1` 카테고리):

| 경로 | 컴포넌트 | 내용 | 셀렉터 |
|---|---|---|---|
| `/sns/seoul` | `SeoulSns.tsx` | 서울시 글로벌 SNS — **fb/ig × en/zh/ja 탭** | `ChannelSelector`(L452) Segmented 탭, 화면 전용 |
| `/sns/posts` | `SnsPosts.tsx` | 전체 게시물 테이블 | 인라인 `Select`(L249), 화면 전용 |
| `/sns/snapshots` | `SnsWeeklySnapshots.tsx` | 주간 팔로워 입력표 | 셀렉터 없음 (전 계정 표) |
| `/sns/accounts` | `SnsAccounts.tsx` | 계정 CRUD + 수집 버튼 | — |
| `/sns/import` | `SnsExcelImport.tsx` | 엑셀 업로드 | — |
| (대시보드) | `dashboards/Marketing1Dashboard.tsx` | 주간 KPI표/성장카드/Top5/**트렌드 placeholder(L587)** | year/month/lang/platform |

- 셀렉터는 **공유 컴포넌트가 아니라 화면마다 중복 구현**(SnsPosts 인라인 Select, SeoulSns ChannelSelector).
  단, 셋 다 `listAccounts()`(`api/sns.ts:187`)를 호출하므로 **데이터는 이미 동적**이다 — DB에 계정을
  추가하면 새로고침 시 모든 화면에 자동 반영된다. "고정처럼 보임"은 UI 분산 + 일부 화면이 플랫폼을
  하드코딩(SeoulSns의 `META_PLATFORMS`)한 탓.
- 차트: **recharts ^2.15.4 설치됨** (`package.json:22`). 이미 `MonthlyChart`(재무),
  `PostMetricsDrawer`(게시물 메트릭 LineChart) 사용 중 → **트렌드 차트에 재사용 가능.**
- 사용자별 위젯/뷰 저장: **없음.** localStorage는 `tk101_dark_mode`, `token`만.

### 1.7 계정 관리 UI/엔드포인트 — Add/Edit 있음, Delete 없음

- 추가: `POST /accounts` + `SnsAccounts.tsx` "계정 추가" 모달 (admin).
- 수정: `PATCH /accounts/{id}` + "계정 수정" 모달.
- 삭제: **하드 DELETE 없음.** `is_active=false` 소프트삭제만 가능. 콘텐츠만 지우는
  `DELETE /accounts/{id}/posts`는 별개.
- 프론트 셀렉터 옵션은 `PLATFORM_OPTIONS`(`api/sns.ts:308`)에서 5개 플랫폼 노출하나,
  자동수집은 `COLLECTABLE_PLATFORMS = {youtube}`만(SnsAccounts.tsx:30) — fb/ig는 수집 버튼이
  현재 비활성(메트릭/댓글은 internal 크론 경유).

---

## 2. 통합 대시보드 설계

### 2.1 목표

5개 `/sns/*` 화면을 **1개 `/sns` 통합 대시보드**로 모으되, 기존 상세 화면은 "드릴다운"으로 남긴다.
한 페이지에서 **모든 플랫폼 × 모든 계정**의 팔로워/게시물/조회수/참여를 보고, **전체 갱신 버튼 1개**로
모두 갱신한다.

### 2.2 레이아웃 (bento/계층형, 단조로운 카드 그리드 금지)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 헤더: "마케팅1팀 SNS 통합"   [기간▾][어권▾][플랫폼▾]  [⟳ 전체 갱신] │  ← 갱신 버튼 = primary, 우상단 고정
├───────────────┬───────────────┬───────────────┬───────────────┬─────┤
│ 총 팔로워     │ 이번주 게시물 │ 총 조회수     │ 평균 참여율   │ 갱신│  ← 상단 요약 스트립(전 플랫폼 합산 + Δ)
│ 1.2M  ▲2.1%  │ 14건  ▲3      │ 480K  ▲12%    │ 4.8%  ▼0.3%   │ 시각│
├───────────────┴───────┬───────┴───────────────┴───────────────┴─────┤
│ [플랫폼별 카드 행: YouTube | Facebook | Instagram]                   │  ← 계정 수만큼 동적 생성
│  각 카드: 아이콘·핸들·구독/팔로워·주간 Δ·게시물수·미니 스파크라인    │     (1.2의 listAccounts 기반)
├─────────────────────────────────────┬───────────────────────────────┤
│ 팔로워 추이 (LineChart, 멀티시리즈) │ 인기 콘텐츠 Top 5 (테이블)    │  ← 좌: 트렌드(신규), 우: 기존 top-posts
│  X=주차, 시리즈=채널, 토글 가능     │  플랫폼/어권 필터               │
├─────────────────────────────────────┴───────────────────────────────┤
│ 주간 KPI 테이블 (기존 stats/weekly 피벗, 어권×플랫폼×주차)          │  ← Marketing1Dashboard에서 이식
└─────────────────────────────────────────────────────────────────────┘
```

- **상단 요약 스트립**: 전 플랫폼·전 계정 합산 + 전주 대비 Δ. `stats/growth` + `stats/weekly` 합산으로 산출.
- **플랫폼별 카드 행**: `accounts`를 platform으로 group → 카드 자동 생성. 계정 추가/삭제가 즉시 반영(동적).
- **팔로워 추이**: 1.5의 `stats/trend` placeholder를 실제 구현으로 대체(§4), recharts `LineChart` 재사용.
- 기존 `Marketing1Dashboard`의 위젯(주간 KPI, 성장 카드, Top5)을 이 페이지로 흡수.

### 2.3 "전체 갱신" 버튼 오케스트레이션

**현 `collect-all`(internal, 크론용)을 그대로 쓰지 말고**, 사용자(admin)가 누를 **공개 트리거 +
플랫폼/단계 분리 + 진행률**을 추가한다.

설계 요지:
- 새 엔드포인트 **`POST /api/sns/refresh-all`** (admin, 비-internal). 내부적으로 기존 3개 일괄 로직
  (`_collect_for_account`, `_collect_metrics_for_account`, 선택적 `_collect_comments_for_account`)을
  계정별로 순회 호출 — **기존 함수 100% 재사용.**
- **동기 호출 60s 타임아웃 문제**가 핵심. 전체 갱신은 계정×게시물이 많아 단일 동기 요청으로 끝낼 수 없다.
  두 가지 안:

  **안 A (권장, 단순): 작업(job) 비동기 + 폴링**
  1. `POST /api/sns/refresh-all` → `refresh_job` 행 1개 생성, 즉시 `job_id` 반환(202).
  2. 백그라운드(FastAPI `BackgroundTasks` 또는 기존 임베딩 잡 패턴의 워커)에서 계정별 순차 수집.
     계정마다 `refresh_job_item` 진행/성공/실패 기록.
  3. 프론트는 `GET /api/sns/refresh-all/{job_id}`를 2~3초 폴링 → 진행 바 + 계정별 상태 표시.
  4. 완료 시 대시보드 데이터 재요청(react-query invalidate).

  **안 B (최소 변경): 클라이언트 오케스트레이션**
  - 프론트가 계정 목록을 받아 **계정별로 `collect/{id}` + `collect-metrics`를 병렬(동시 3~4개로 제한)
    호출**하고, 각 응답을 진행률에 반영. 서버 신규 코드 없이 기존 엔드포인트만 사용.
  - 단점: 브라우저 탭에 묶임(닫으면 중단), 진행 상태가 서버에 안 남음. → **MVP엔 B, 정식은 A.**

- **순차 vs 병렬**: 같은 Meta 토큰을 공유하는 fb/ig는 **순차**(레이트리밋·토큰 동시성), 서로 다른
  플랫폼(yt vs meta)은 **병렬 허용**. 안 A 서버에서 플랫폼별 세마포어로 제어.
- **부분 실패**: `collect-all`의 격리 패턴(L1330) 그대로. job 결과에 `{account, step, ok, error}` 배열을
  담아 "유튜브 영문 ✅ / 인스타 일문 ⚠️ 토큰만료" 식으로 표면화.
- **단계 범위**: 갱신 = (1) collect(게시물+팔로워 스냅샷) → (2) collect-metrics(fb/ig) →
  (3) 선택적 collect-comments. 버튼에 "팔로워/게시물만 빠르게" vs "메트릭·댓글까지 전체" 옵션 토글.

---

## 3. 계정 CRUD + 동적 셀렉터

### 3.1 데이터 모델

**변경 불필요.** `SocialAccount`(§1.1)가 platform/handle/page_url/external_id/credential 메타를
이미 보유. 플랫폼별 필요한 식별자:

| platform | 필요한 값 |
|---|---|
| youtube | `handle`(@핸들) 또는 `external_id`(채널ID) 또는 `page_url`. 토큰은 전역 `GOOGLE_YOUTUBE_API_KEY` |
| facebook | `external_id`(Page ID, 권장) 또는 `page_url`/`handle`. 토큰은 전역 `META_ACCESS_TOKEN` |
| instagram | `external_id`(IG business ID) 또는 `handle`/`page_url`. 토큰은 전역 `META_ACCESS_TOKEN` |

- **자격증명은 계정별이 아니라 전역 env**다(YouTube 키 1개, Meta 토큰 1개로 모든 페이지 접근).
  따라서 계정 CRUD는 식별자(handle/external_id/page_url)만 다루면 된다. 향후 계정별 토큰이 필요해지면
  `extra_metadata(JSONB)`에 암호화 저장 슬롯이 이미 있다.

### 3.2 엔드포인트 — 1개만 추가

- 기존: `GET/POST/PATCH /api/sns/accounts` 유지.
- **추가: `DELETE /api/sns/accounts/{account_id}`** (admin).
  - FK `ON DELETE CASCADE`(posts→metrics/comments)가 이미 걸려 있어 행 삭제 시 하위 데이터 정리됨.
  - **권장 기본은 소프트삭제 유지** + 하드삭제는 `?hard=true`로 분리. 기본 호출은 `is_active=false`,
    `hard=true`면 실제 `DELETE`(수집 이력까지 영구 제거 — 모달에서 명시적 경고).
  - 이유: 수집된 트렌드/이력 보존이 중요(백워드 호환). "자유로운 삭제"는 UI상 소프트삭제로 충분한 경우가 많음.

### 3.3 동적 셀렉터 — 공유 컴포넌트로 통일

문제: 셀렉터가 화면마다 중복(SnsPosts 인라인 Select, SeoulSns ChannelSelector), 일부는 플랫폼 하드코딩.

해결:
- **`AccountSelector` 공유 컴포넌트 신설**(`frontend/src/components/sns/AccountSelector.tsx`).
  - props: `value/onChange`, `mode`("single"|"multi"), `filterPlatform?`, `filterLanguage?`.
  - 내부에서 `listAccounts()` 호출(또는 react-query로 캐시 공유) → **DB 계정만으로 옵션 구성.**
  - 라벨은 기존 `buildAccountLabel`(SnsPosts:54) 패턴: `유튜브 · @handle`.
- 모든 SNS 화면이 이 컴포넌트를 쓰도록 교체 → 계정 추가/삭제가 **모든 곳에 자동 반영.**
- 플랫폼 옵션도 하드코딩(`META_PLATFORMS`) 대신 **현재 계정 집합에서 distinct platform**으로 파생.
- 권장: 계정 목록을 **react-query 단일 캐시 키(`['sns-accounts']`)**로 공유 → CRUD 후 invalidate
  하면 셀렉터·카드·대시보드가 한 번에 갱신.

---

## 4. 메트릭 + 트렌드

### 4.1 플랫폼별 메트릭 세트

| 지표 | YouTube | Facebook | Instagram | 출처 |
|---|---|---|---|---|
| 구독자/팔로워 | ✅ 구독자 | ✅ | ✅ | `SocialWeeklySnapshot.followers` |
| 게시물 수 | ✅ | ✅ | ✅ | `SocialPost` count |
| 조회수 | ✅ | △(일반 게시물 미제공) | ✅ | `view_count` / metric snapshot |
| 도달 | ❌ | ✅ insights | ✅ insights | `reach_count` |
| 좋아요/댓글/공유 | ✅(공유 ❌) | ✅ | ✅(공유 △) | post 컬럼 |
| 참여(engagement) | 합산 | 합산 | 합산 | `total_engagement` |

대시보드는 **플랫폼별로 제공되는 지표만 표시**하고, 미제공은 "-"로(서버 write-back이 이미 None
보존, `_writeback_post_metrics` L722). YouTube엔 도달 컬럼을 숨긴다.

### 4.2 트렌드 — 기존 스냅샷 메커니즘 활용 + `stats/trend` 구현

- **팔로워 추이**: `SocialWeeklySnapshot`이 이미 (account, year, month, week) 시계열을 보유. 새 테이블
  불필요. `GET /api/sns/stats/trend`(현재 빈 배열, L456)를 다음으로 구현:
  - 입력: `language?`, `platform?`, `account_id?`, 기간(개월 수).
  - 출력: `[{ period: "2026-05-W3", account/platform/language, followers }]` 정렬 시계열.
  - 멀티 계정 합산 옵션(전체 팔로워 추이) + 채널별 시리즈 옵션.
- **게시물 메트릭 추이**: `SocialPostMetricSnapshot`(daily/weekly) + 기존
  `GET /posts/{id}/metrics`(L948) → `PostMetricsDrawer.tsx`가 이미 LineChart로 렌더. 대시보드의
  "콘텐츠 추이" 위젯은 이 드릴다운으로 연결.
- **차트**: recharts 재사용. 신규 `FollowerTrendChart`(멀티 라인, 시리즈=채널, 토글). MonthlyChart의
  다크모드/툴팁 패턴 답습.

### 4.3 갱신 시 스냅샷 적재

전체 갱신이 도는 순간 `_collect_for_account`(L583)가 그 주차 `SocialWeeklySnapshot`을 upsert(L630),
`_upsert_metric_snapshot`(L782)이 게시물 메트릭을 (post, period, 오늘) 멱등 적재. → **갱신 1회로 추이
포인트가 1개씩 누적**되어 트렌드가 자연스럽게 채워진다. (별도 적재 로직 불필요.)

---

## 5. 사용자 설정 가능(자유도)

업무가 자주 바뀌므로 **단순하지만 유연하게**. 무거운 위젯 빌더 금지.

### MVP (localStorage, 서버 0)
- 대시보드 상단 "위젯 표시" 토글(체크박스 그룹): 요약 스트립 / 플랫폼 카드 / 팔로워 추이 / Top5 / 주간 KPI.
- 기본 필터(어권/플랫폼/기간) + 위젯 on/off + 위젯 순서를 **`localStorage['tk101_sns_dashboard_view']`**
  에 저장(기존 `tk101_dark_mode` 패턴 답습). 사용자/브라우저 단위.

### 정식 (서버 저장, 다기기 동기화 필요 시)
- 신규 테이블 `user_dashboard_views(user_id, dashboard_key, config JSONB)` + `GET/PUT /api/me/dashboard-views/{key}`.
- config JSONB: `{ widgets: [...], order: [...], filters: {...} }`. 자유 확장.
- 여러 "뷰" 저장(예: "주간보고용", "광고검토용")하고 드롭다운으로 전환.

권장: **MVP부터.** 위젯 토글+필터 저장만으로 자유도 체감 대부분 충족. 서버 뷰는 수요 확인 후.

---

## 6. 마이그레이션/롤아웃 (단계별 PR, 빅뱅 금지)

| PR | 범위 | 재사용 / 신규 | DB 변경 | 백워드 호환 |
|---|---|---|---|---|
| **PR-1** 계정 DELETE + 동적 셀렉터 | `DELETE /accounts/{id}`(soft/hard) + 프론트 `AccountSelector` 공유 컴포넌트, SnsAccounts에 삭제 버튼 | 재사용: 기존 CRUD·CASCADE FK / 신규: DELETE 핸들러, 컴포넌트 | 없음(스키마 그대로) | 기존 PATCH 소프트삭제 유지 |
| **PR-2** `stats/trend` 구현 + 트렌드 차트 | 팔로워 추이 엔드포인트 + `FollowerTrendChart`, Marketing1Dashboard 트렌드 placeholder 대체 | 재사용: `SocialWeeklySnapshot`, recharts·PostMetricsDrawer 패턴 / 신규: trend 쿼리, 차트 | 없음 | placeholder만 교체 |
| **PR-3** 통합 대시보드 페이지 `/sns` | 요약 스트립+플랫폼 카드+위젯 흡수. 기존 `/sns/*` 상세는 드릴다운 유지 | 재사용: stats/weekly·growth·top-posts·trend / 신규: 페이지·요약 합산 | 없음 | 기존 화면 라우트 보존 |
| **PR-4** 전체 갱신 (MVP=안B) | 대시보드 "전체 갱신" 버튼 = 클라이언트 오케스트레이션(병렬 제한+진행률) | 재사용: `collect/{id}`, `collect-metrics` / 신규: 프론트 오케스트레이터 | 없음 | 서버 무변경 |
| **PR-5** 전체 갱신 정식 (안A) | `refresh-all` 비동기 잡 + 진행 폴링 | 재사용: `_collect_for_account` 등 일괄 로직 / 신규: `refresh_job(_item)` 테이블·워커·폴링 | **신규 2테이블** | PR-4 버튼이 새 엔드포인트로 스위치 |
| **PR-6** 사용자 뷰 저장 (선택) | 위젯 토글/순서 localStorage→(필요 시)서버 | 신규: `user_dashboard_views` | 선택적 1테이블 | 없으면 localStorage만 |

- **재사용 비중이 매우 높다**: 데이터 모델·수집기·통계 엔드포인트·차트 라이브러리·CRUD·격리 패턴이
  전부 존재. 신규는 ① 계정 DELETE ② trend 구현 ③ 통합 페이지 ④ 갱신 오케스트레이션 ⑤ (선택) 뷰 저장.
- 기존 엑셀 임포트·n8n 크론과 **공존**: 전체 갱신 버튼은 크론을 대체하지 않고 "지금 즉시" 경로만 추가.

---

## 7. 리스크

1. **API 레이트리밋 (전체 갱신)**: 계정 많아지면 Meta/YouTube 쿼터 소진. 완화: 플랫폼별 세마포어(fb/ig
   순차), `_QUICK_MAX_PAGES` 상한 유지, 백오프, "빠른 갱신"(메트릭/댓글 생략) 기본값.
2. **Meta 토큰 만료**: 장기 토큰도 만료/권한변경 가능 → 전체 갱신 중 503. 완화: `meta/whoami`(L120)로
   사전 진단 배지, 토큰 만료 시 해당 플랫폼만 실패 격리하고 나머지 진행, 대시보드에 "토큰 점검 필요" 경고.
3. **부분 데이터**: 플랫폼별 미제공 지표(YouTube 도달, FB 일반게시물 조회수). 완화: 합산 시 None 제외,
   UI는 "-" 표기 + 미니 안내. `_writeback`이 None 보존하므로 데이터 오염 없음.
4. **동기 60s 타임아웃**: 클라이언트 오케스트레이션(안 B)이 한 요청에 모든 계정을 처리하려 하면 위험.
   → 계정별 개별 요청으로 분할(이미 상한 적용됨), 정식은 비동기 잡(안 A).
5. **하드삭제 데이터 손실**: 계정 DELETE `hard=true`는 트렌드 이력까지 CASCADE 삭제. 완화: 기본 소프트삭제,
   하드삭제는 명시적 더블컨펌 모달.
6. **셀렉터 통일 시 회귀**: SeoulSns의 어권×플랫폼 탭 UX를 공유 컴포넌트로 옮길 때 기존 동작 유지 필요.
   완화: `AccountSelector`에 `mode="segmented"` 옵션으로 기존 ChannelSelector 거동 흡수, 점진 교체.

---

## 부록 A. 핵심 파일 경로

- 모델: `backend/app/models/sns.py`
- 라우터: `backend/app/routers/sns.py` (공개 + `internal_router`)
- 스키마: `backend/app/schemas/sns.py`
- 수집기: `backend/app/services/sns_collectors/{youtube,facebook,instagram,meta_graph}.py`
- 임포터: `backend/app/services/sns_importers/marketing1.py`
- 설정: `backend/app/config.py` (L10 youtube key, L20 meta token, L14 internal token)
- n8n 크론: `n8n_workflows/{youtube_daily,sns_meta_metrics_daily,sns_meta_metrics_weekly}.json`
- 프론트 API: `frontend/src/api/sns.ts`
- 프론트 화면: `frontend/src/pages/marketing/{SeoulSns,SnsPosts,SnsWeeklySnapshots,SnsAccounts,SnsExcelImport}.tsx`
- 대시보드: `frontend/src/pages/dashboards/Marketing1Dashboard.tsx`
- 차트 재사용: `frontend/src/components/finance/MonthlyChart.tsx`, `frontend/src/pages/marketing/PostMetricsDrawer.tsx`
- 라우팅/메뉴: `frontend/src/App.tsx:158`, `frontend/src/config/modules.tsx:102`
