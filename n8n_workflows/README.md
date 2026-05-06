# n8n 워크플로 템플릿

TK101 AI 백엔드와 연동되는 자동화 워크플로 모음입니다.

## youtube_daily.json — SNS 주간 수집 (Mon 05:00 KST)

매주 월요일 05:00 KST(`0 20 * * 0` UTC) 실행되어 자동 수집 가능 플랫폼(현재 YouTube만)인
모든 활성 SocialAccount를 일괄 수집합니다.

- **호출**: `POST http://backend:8000/api/internal/sns/collect-all`
- **인증**: `X-Internal-Token` 헤더 (n8n 환경변수 `TK101_INTERNAL_TOKEN`)
- **동작**: 백엔드가 직접 YouTube API 호출 → DB 저장. n8n은 cron + 호출만.

### Import 방법

1. n8n 콘솔(http://43.155.202.112:5678) 접속
2. 좌측 상단 메뉴 → **Workflows** → **Import from File** → `youtube_daily.json` 선택
3. n8n 환경변수에 `TK101_INTERNAL_TOKEN` 등록
   - **방법 A (권장)**: 워크플로 **Settings** → Variables → `TK101_INTERNAL_TOKEN` 추가
   - **방법 B**: `docker-compose.yml` 의 n8n 서비스 environment 에 `TK101_INTERNAL_TOKEN: ${TK101_INTERNAL_API_TOKEN}` 추가 후 컨테이너 재시작
   - 값은 GitHub Secrets에 등록한 `TK101_INTERNAL_API_TOKEN` 과 동일
4. 워크플로 우상단 **Active** 토글 ON
5. **Executions** 탭에서 다음 월요일 05:00 KST 실행 결과 확인

### 동작 메모

- 매주 1회라 quota 부담 없음 (무료 일 10,000 unit 중 수십 unit 사용)
- SNS 계정에 채널 핸들이나 URL만 입력해도 백엔드가 자동으로 channel ID 변환 → external_id에 저장
- 한 계정 실패해도 다른 계정 수집은 계속 (전체 실패 시에만 502)

### TODO

- [ ] 실패 시 Slack/Telegram 알림 노드 추가
- [ ] Facebook/Instagram Collector 추가되면 SUPPORTED_PLATFORMS 자동 확장 (백엔드만 수정, 워크플로 그대로)

## T5 범용 문서 자동 작성기 워크플로

T5 트랙(`업무개선요구사항/PRD/T5_범용문서자동작성기_PRD.md` §13.4)에 정의된 3개 워크플로.
모두 백엔드 `/api/forms/*` 엔드포인트만 호출하며, 비즈니스 로직은 백엔드가 보유.

### t5_form_analyze.json — T5 양식 분석 (v0.1)

- **트리거**: Webhook `POST /webhook/t5-form-analyze` (동기, 타임아웃 180s)
- **호출**: `POST http://backend:8000/api/forms/templates/analyze`
- **용도**: 업로드된 양식 파일을 분석해 변수 목록 추출 (FR-01)
- **인증**: `X-Internal-Token` 헤더

### t5_form_map.json — T5 자료 매핑 (v0.1)

- **트리거**: Webhook `POST /webhook/t5-form-map` (비동기, 타임아웃 600s)
- **호출**: `POST http://backend:8000/api/forms/jobs/{job_id}/run_mapping` → 완료 후 `callback_url` 콜백
- **요청 페이로드**: `{ "job_id": "...", "callback_url": "https://..." }`
- **용도**: 장시간 매핑 작업 비동기 실행 (FR-04). 콜백 노드가 결과를 호출자에게 전달

### t5_cleanup_expired.json — T5 만료 자료 자동 삭제 (v0.1)

- **Schedule**: `0 18 * * *` UTC (매일 03:00 KST)
- **호출**: `POST http://backend:8000/api/forms/cleanup`
- **용도**: 30일 경과 양식/매핑 자료 자동 삭제 (FR-12, T5-D §13.4)

### Import 절차 (T5 일괄)

1. n8n 콘솔 → Workflows → Import from File → 위 3개 JSON 순서대로
2. `TK101_INTERNAL_TOKEN` 환경변수가 이미 등록되어 있으면 추가 설정 불필요 (youtube_daily.json 과 공유)
3. 각 워크플로 우상단 Active 토글 ON
4. 양식 분석/매핑은 백엔드에서 webhook URL 호출, cleanup은 다음 03:00 KST 자동 실행

## 새 워크플로 추가 시

- `n8n_workflows/` 폴더에 JSON 추가 + 이 README에 설명 한 줄 추가
- Schedule + HTTP Request 2-노드 구조 권장 (비즈니스 로직은 백엔드에)
