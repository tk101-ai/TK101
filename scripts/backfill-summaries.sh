#!/usr/bin/env bash
# v0.7.x — 모든 nas_files에 Claude Haiku 4.5 키워드 요약 청크(chunk_index=-2) 추가/갱신.
# 본문/파일명 청크와 함께 cosine 매칭되어 검색 hit율 향상.
#
# 비용 추산: 12K 파일 × Haiku 4.5 (input ~1K + output ~150 token) ≈ $15~20
# 시간 추산: 동시성 3 + Anthropic 평균 응답 ~2~4초 → 약 2~4시간
#
# 사용:
#   ./scripts/backfill-summaries.sh
#   nohup ./scripts/backfill-summaries.sh > /tmp/backfill-summaries.log 2>&1 &
#
# 실행 권한: chmod +x scripts/backfill-summaries.sh
set -uo pipefail

cd "$(dirname "$0")/.."

API="${API_URL:-http://localhost:8000}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"

TOKEN=$(./scripts/admin-token.sh)
if [ -z "$TOKEN" ]; then
  echo "ERROR: admin 토큰 발급 실패" >&2
  exit 1
fi

echo "[요약 backfill 시작] 비용 추산 ≈ \$15~20 (12K 파일, Haiku 4.5)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API}/api/nas/index/backfill_summaries" \
  -H "Authorization: Bearer $TOKEN")
BODY=$(echo "$RESPONSE" | head -n -1)
CODE=$(echo "$RESPONSE" | tail -n 1)

if [ "$CODE" != "202" ]; then
  echo "ERROR: backfill 시작 실패 (HTTP $CODE)" >&2
  echo "$BODY" >&2
  exit 1
fi
echo "응답: $BODY"

echo
echo "[진행률 폴링 — ${POLL_INTERVAL}초 간격]"
START=$(date +%s)
while true; do
  POLL_TOKEN=$(./scripts/admin-token.sh 2>/dev/null) || {
    echo "WARN: 토큰 발급 실패. 5초 후 재시도."
    sleep 5
    continue
  }
  STATUS=$(curl -fsS -H "Authorization: Bearer $POLL_TOKEN" "${API}/api/nas/index/summary_status" 2>/dev/null) || {
    echo "WARN: 진행률 조회 실패. 5초 후 재시도."
    sleep 5
    continue
  }
  RUNNING=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['running'])")
  PROCESSED=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['processed'])")
  TOTAL=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
  ERRORS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['errors'])")
  ELAPSED=$(( $(date +%s) - START ))
  printf "[%5ds] processed=%d/%d, errors=%d, running=%s\n" \
    "$ELAPSED" "$PROCESSED" "$TOTAL" "$ERRORS" "$RUNNING"
  if [ "$RUNNING" != "True" ]; then
    echo
    echo "[backfill 종료]"
    echo "$STATUS" | python3 -m json.tool
    break
  fi
  sleep "$POLL_INTERVAL"
done
