# BACKLOG — TK101

할 일을 여기에 적어두면 Claude가 우선순위 높은 것부터 **자율로 구현·배포·검증**한다(작업 방식: 루트 `CLAUDE.md`).
표시: `[ ]` 대기 · `[~]` 진행중 · `[x]` 완료(PR#) · `⚠️오너승인` = 시작 전 확인 필요(파괴적/고비용).

> 사용법: 그냥 아래에 한 줄씩 추가하면 됨. 큰 항목은 하위 `-`로 쪼개도 좋음. 우선순위는 위→아래.

---

## NOW (다음 세션에 바로)
- [ ] **코드리뷰 커버리지 검증 패스** (오너 질문 후속) — 전체 리뷰가 *범위*는 전부 커버했으나 71K LOC를 전 줄 정독한 건 아님(큰 파일 위주). 전 파일 체크리스트로 "모든 파일에 눈이 닿았나" 확정 + 빠진 파일만 추가 리뷰. (`pages/Transactions.tsx`처럼 글롭 밖 파일 점검)
- [x] **품질 P1 (1차) 완료** — sns.py 2173→패키지, forms.py 1350→패키지, Transactions.tsx 1114→254, SessionDetailPage 1070→171. 라우트 보존(OpenAPI 검증). ⚠️배포 1회 실패(tsc -b 미사용import)→`npm run build` 검증으로 전환.
- [x] **품질 P1 (2차) 완료·배포** — playground.py 1412→패키지(라우트27 보존) · session_service.py 997→패키지(15 공개API 보존) · ProductsPage 930→123 · Marketing1Dashboard 888→120 · AnalyticsPage 871→181 · MediaGenPanel 835→446. OpenAPI 188경로 보존. npm run build 배포전 검증(빌드실패 0). **→ P1 거대파일 10개 전부 분할 완료.**
- [x] **커버리지 발견 보완 완료·배포(~20건)** — ProtectedRoute role 가드+/users admin게이트 · streamChat 입력잠김 해결 · 첨부 clear · TaxInvoices 자동조회·NaN가드 · Transactions bulk 동시성캡+부분성공·죽은코드 · Register 검증 · reconcile 후보집합 정정(중복청구) · upload_log 스키마 · balance N+1→단일쿼리 · attachments uuid. npm run build 검증.
- [ ] ⚠️논의 **#1 localStorage JWT → httpOnly 쿠키** (커버리지서도 재확인된 HIGH) — 인증 저장모델 변경, 로그인 흐름 위험. 별도 논의 후 (= 기존 C 항목과 동일)
- [ ] **품질 P3 — 일관성/플랫폼** (점진): BE 에러 한국어 통일·uuid 통일 · FE 라우트 데이터주도(NAV 단일소스) · TanStack Query 도입 · 데드코드 제거(file_walker.py 등)

## NEXT (조만간)
- [ ] **포매터/린터 셋업** — prettier(frontend) + ruff/black(backend) 추가. 현재 미설치라 ECC 품질 훅(`stop:format-typecheck` 등) 포매터 절반이 no-op. 깔면 자동포맷·린트 살아남
- [ ] **SNS 수동 분류(`구분`) 입력 필드** — 게시물에 행사/기획/정책/이벤트/기타 수동 입력 + 콘텐츠현황/콘텐츠 화면에서 필터·집계 (API로 못 긁는 부분)
- [ ] **제작주체 집계** — `producer`(서울시제공/TK제작/인플루언서) 필드 이미 있음, 대시보드/현황에 집계·표시
- [ ] **엑셀 내보내기 (B)** — 부서(dept) 대신 NAS 폴더명(MARKETING/COMPANY/CLOUD/RND)으로 표기: 파이프라인에 `top_folder` 페이로드 필드 추가 후 폴더 단위 표기
- [ ] **docwork PR-C** — 검수(LLM-judge)·렌더를 form_filler와 공유화, `form_filler/extractor`를 `services/documents/`로 이전

## 전체 코드리뷰 후속 (2026-06-22, → docs/reviews/CODE_REVIEW_FULL_2026-06-22.md)
- [x] **그룹1 + D 보완 완료 — PR#59 배포** — 입력검증→422 · path통일 · React버그(대량fetch/regex/디바운스/5주차) · pool_pre_ping · IntegrityError→409 · 토큰무효화 · 매칭 불변식(E1) · 에러메시지 일관 · 하드코딩 + #1~5 + D 레이트리밋(로그인·LLM·생성, 신사업팀 접근 보존). 6에이전트 병렬→통합→검증→배포
- [ ] **G2 후속**: ProductsPage 서버사이드 페이지네이션(이번엔 cap+경고만, 회사별집계 때문에 보류) · MappingTable 부분갱신(키스토크 디바운스는 완료, 부모 PATCH+refetch는 남음)
- [ ] **H3 후속**: `UserCreate.password` min/max_length (schemas/user.py — 소유밖이라 미처리)
- [ ] ⚠️논의 **C: localStorage JWT → httpOnly 쿠키 단일화** — XSS 방어 강화지만 로그인 흐름 변경 위험, 신중히 테스트 후 (보류, 추후 논의)
- [ ] ⚠️논의 **S-1: 테스트 인프라 구축** — 인증·금액·매칭 핵심 로직 pytest/vitest 안전망(현재 8개뿐). 보완의 전제조건이라 별도 큰 작업
- [ ] **결정기록**: NAS검색 = **전사 공유 유지**(부서 스코핑 OFF 의도적). confidential 플래그 필터링은 추후 검토. by-path 다운로드 인가도 추후.
- [ ] 나머지 medium/low (토큰무효화 J·세션확장성 K 등) — 리뷰 문서 부록 참조, 우선순위 낮음
- [ ] **SNS 데이터 퀄리티** — 과거 게시물/메트릭 backfill(메타·유튜브 API 깊이 긁기), 누락 메트릭 보정
- [ ] **릴스 캠페인 추적** — 차수/EP/주제 + 크로스플랫폼(웨이보·페북) 성과 비교 (시트의 릴스 시리즈 탭)
- [ ] **보고서 생성** — 항목별 보고서 양식 맞춤 (⚠️ 오너가 양식 전달 후 착수)

## ⚠️ 오너 승인/입력 필요 (시작 전 확인 — 콘솔/계정/파괴/고비용)
- [ ] ⚠️오너승인 **보안 조치** — open-webui :3000 공개차단(가입 OFF), SSH 하드닝(fail2ban·비번/root off), backend-dev 8001 바인딩 수정, WireGuard 직원별 키, Cloudflare Tunnel. 콘솔/계정 작업 다수. → `docs/reviews/REVIEW_SECURITY_DOMAIN_CLEANUP_2026-06-22.md`
- [ ] ⚠️오너승인 **디스크 정리 ~50GB** — `docker image prune -f` + `docker builder prune -f` 등 SAFE 후보 + tk101-dev-nas(stale) 제거. (파괴적이라 승인 후)
- [ ] ⚠️오너승인 **금요일 18시 임베딩 스케줄** — RunPod 서버리스 + Qdrant 접근방식(푸시 모델 권장) 결정 필요. → `docs/reviews/REVIEW_INCREMENTAL_EMBEDDING_FRIDAY_SCHEDULE.md`

## DONE (최근)
- [x] NAS 검색 부서 필터(Qdrant 다중선택, RND 포함) — PR#56
- [x] SNS 콘텐츠 채널 셀렉터 제거, 계정 선택기 일원화 — PR#55
- [x] 엑셀 내보내기 1·2단계(페이지별 + 브랜드별 통합워크북) — PR#53/54
- [x] 콘텐츠 현황 페이지(게재건수) — PR#52
- [x] 브랜드(client) 활성화 + 대시보드 채널식별 — PR#51
- [x] SNS 통합·브랜드·권한개방·댓글영속화·버그픽스 — PR#39~50
- [x] 문서작업 통합(docgen 품질·업로드·잡영속화·504픽스) — PR#31~43
- [x] 레거시 pgvector 제거 / docs 폴더 정리 — PR#32/38

> 전체 이력: `docs/worklogs/2026-06-22.md`
