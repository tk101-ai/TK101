#!/usr/bin/env bash
# 라이브 서버에서 admin JWT 토큰 발급. 다른 스크립트에서 $(./scripts/admin-token.sh)로 사용.
# ADMIN_EMAIL / ADMIN_PASSWORD / API_URL env 로 오버라이드 가능.
set -euo pipefail

EMAIL="${ADMIN_EMAIL:-admin@tk101.co.kr}"
PASSWORD="${ADMIN_PASSWORD:-admin123}"
API="${API_URL:-http://localhost:8000}"

curl -fsS -X POST "${API}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
