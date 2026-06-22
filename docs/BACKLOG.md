# BACKLOG — TK101

할 일을 여기에 적어두면 Claude가 우선순위 높은 것부터 **자율로 구현·배포·검증**한다(작업 방식: 루트 `CLAUDE.md`).
표시: `[ ]` 대기 · `[~]` 진행중 · `[x]` 완료(PR#) · `⚠️오너승인` = 시작 전 확인 필요(파괴적/고비용).

> 사용법: 그냥 아래에 한 줄씩 추가하면 됨. 큰 항목은 하위 `-`로 쪼개도 좋음. 우선순위는 위→아래.

---

## NOW (다음 세션에 바로)
- [ ] (여기에 가장 급한 것)

## NEXT (조만간)
- [ ] **포매터/린터 셋업** — prettier(frontend) + ruff/black(backend) 추가. 현재 미설치라 ECC 품질 훅(`stop:format-typecheck` 등) 포매터 절반이 no-op. 깔면 자동포맷·린트 살아남
- [ ] **SNS 수동 분류(`구분`) 입력 필드** — 게시물에 행사/기획/정책/이벤트/기타 수동 입력 + 콘텐츠현황/콘텐츠 화면에서 필터·집계 (API로 못 긁는 부분)
- [ ] **제작주체 집계** — `producer`(서울시제공/TK제작/인플루언서) 필드 이미 있음, 대시보드/현황에 집계·표시
- [ ] **엑셀 내보내기 (B)** — 부서(dept) 대신 NAS 폴더명(MARKETING/COMPANY/CLOUD/RND)으로 표기: 파이프라인에 `top_folder` 페이로드 필드 추가 후 폴더 단위 표기
- [ ] **docwork PR-C** — 검수(LLM-judge)·렌더를 form_filler와 공유화, `form_filler/extractor`를 `services/documents/`로 이전

## LATER (더 큰 것)
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
