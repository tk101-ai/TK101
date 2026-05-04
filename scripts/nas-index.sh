#!/usr/bin/env bash
# 단일 폴더 NAS 인덱싱 트리거 + 진행률 자동 폴링. 인덱싱 끝까지 기다린다.
# 사용: ./scripts/nas-index.sh "TENCENT CLOUD"        # subdir 지정
#       ./scripts/nas-index.sh                       # 전체 (위험: 매우 김)
#       ./scripts/nas-index.sh "MARKETING/04_업무 메뉴얼 (★)" --full   # full_rescan
set -uo pipefail

cd "$(dirname "$0")/.."

SUBDIR="${1:-}"
FULL_RESCAN="false"
if [ "${2:-}" = "--full" ] || [ "${1:-}" = "--full" ]; then
  FULL_RESCAN="true"
  if [ "${1:-}" = "--full" ]; then SUBDIR="${2:-}"; fi
fi

API="${API_URL:-http://localhost:8000}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"

TOKEN=$(./scripts/admin-token.sh)
if [ -z "$TOKEN" ]; then
  echo "ERROR: admin 토큰 발급 실패" >&2
  exit 1
fi

# JSON payload 안전하게 빌드 (한글/공백/특수문자 대응 — python으로 직렬화)
PAYLOAD=$(python3 -c "
import json, sys
sub = sys.argv[1] or None
full = sys.argv[2] == 'true'
body = {'full_rescan': full}
if sub:
    body['subdir'] = sub
print(json.dumps(body, ensure_ascii=False))
" "$SUBDIR" "$FULL_RESCAN")

LABEL="${SUBDIR:-(전체)}"
echo "[인덱싱 시작] $LABEL  (full_rescan=$FULL_RESCAN)"
echo "payload: $PAYLOAD"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API}/api/nas/index/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD")
BODY=$(echo "$RESPONSE" | head -n -1)
CODE=$(echo "$RESPONSE" | tail -n 1)

if [ "$CODE" != "202" ]; then
  echo "ERROR: 인덱싱 시작 실패 (HTTP $CODE)" >&2
  echo "$BODY" >&2
  exit 1
fi
echo "응답: $BODY"

echo
echo "[진행률 폴링 — ${POLL_INTERVAL}초 간격]"
START=$(date +%s)
while true; do
  STATUS=$(curl -fsS -H "Authorization: Bearer $TOKEN" "${API}/api/nas/index/status" 2>/dev/null) || {
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
    echo "[인덱싱 종료] $LABEL"
    echo "$STATUS" | python3 -m json.tool
    break
  fi
  sleep "$POLL_INTERVAL"
done
