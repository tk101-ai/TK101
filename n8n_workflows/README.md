# n8n 워크플로 템플릿

TK101 AI 백엔드와 연동되는 자동화 워크플로 모음입니다.

## youtube_daily.json — YouTube 일일 수집

매일 03:00 KST(UTC 18:00)에 백엔드 수집 API를 호출합니다.

### Import 방법

1. n8n UI 접속 → 우상단 메뉴 → **Import from File** → `youtube_daily.json` 선택
2. **Set account_id** 노드를 열어 `<YOUR_ACCOUNT_ID>` 자리에 실제 SNS 계정 ID(UUID) 입력
3. n8n 환경변수에 `TK101_INTERNAL_TOKEN` 등록 (Settings → Variables 또는 docker-compose `environment`)
4. 워크플로 우상단 토글로 **Active** 전환

### TODO

- [ ] 백엔드 internal token 인증 미들웨어 구현 (현재 placeholder)
- [ ] 실패 시 Slack/Telegram 알림 노드 추가
- [ ] 다계정 일괄 수집 엔드포인트(`/api/sns/collect`) 도입 시 Set 노드 제거
