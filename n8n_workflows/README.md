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

## 새 워크플로 추가 시

- `n8n_workflows/` 폴더에 JSON 추가 + 이 README에 설명 한 줄 추가
- Schedule + HTTP Request 2-노드 구조 권장 (비즈니스 로직은 백엔드에)
