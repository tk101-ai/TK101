#!/usr/bin/env bash
# 부서별 테스트 사용자 1명씩 등록 (총 6명, admin은 기존 계정 사용)
# 필수: ADMIN_PASSWORD env, 선택: API_URL (기본 http://localhost:8000), TEST_USER_PASSWORD (기본 'tk101-test-2026')
#
# 사용법:
#   export ADMIN_PASSWORD='...'
#   ./scripts/seed-test-users.sh
#
# 동일 이메일이 이미 존재하면 409 응답 → "이미 존재" 출력 후 다음 계정 진행.
# 첫 로그인 후 사용자에게 비번 변경 안내 필요.
set -uo pipefail

cd "$(dirname "$0")/.."

API="${API_URL:-http://localhost:8000}"
PASSWORD="${TEST_USER_PASSWORD:-tk101-test-2026}"

# admin 토큰 발급 (admin-token.sh가 ADMIN_PASSWORD 미설정 시 에러 처리함)
echo "=== admin 토큰 발급 ==="
TOKEN="$(./scripts/admin-token.sh)"
if [ -z "${TOKEN:-}" ]; then
  echo "ERROR: admin 토큰 발급 실패. ADMIN_PASSWORD 확인." >&2
  exit 1
fi
echo "토큰 OK (${#TOKEN}자)"
echo

# 부서별 더미 계정: "department|email|name"
USERS=(
  "marketing_1|test-marketing1@tk101.co.kr|김마케원"
  "marketing_2|test-marketing2@tk101.co.kr|박마케투"
  "new_business|test-newbiz@tk101.co.kr|이사업"
  "finance|test-finance@tk101.co.kr|최재무"
  "new_media|test-newmedia@tk101.co.kr|정미디"
  "design|test-design@tk101.co.kr|한디자"
)

echo "=== 계정 생성 시작 (총 ${#USERS[@]}명) ==="
CREATED=()
SKIPPED=()
FAILED=()

for ENTRY in "${USERS[@]}"; do
  IFS='|' read -r DEPT EMAIL NAME <<< "$ENTRY"

  PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
    'email': '${EMAIL}',
    'password': '${PASSWORD}',
    'name': '${NAME}',
    'department': '${DEPT}',
    'role': 'member',
}))
")

  HTTP_CODE=$(curl -sS -o /tmp/seed-user-resp.json -w "%{http_code}" \
    -X POST "${API}/api/users" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "${PAYLOAD}" || echo "000")

  case "${HTTP_CODE}" in
    201)
      echo "  [생성] ${DEPT} / ${EMAIL} / ${NAME}"
      CREATED+=("${EMAIL}")
      ;;
    409)
      echo "  [SKIP] ${DEPT} / ${EMAIL} — 이미 존재"
      SKIPPED+=("${EMAIL}")
      ;;
    *)
      echo "  [실패] ${DEPT} / ${EMAIL} — HTTP ${HTTP_CODE}"
      cat /tmp/seed-user-resp.json 2>/dev/null || true
      echo
      FAILED+=("${EMAIL}")
      ;;
  esac
done

echo
echo "=== 결과 요약 ==="
echo "생성: ${#CREATED[@]}건"
echo "스킵: ${#SKIPPED[@]}건"
echo "실패: ${#FAILED[@]}건"

echo
echo "=== 운영팀 전달용 계정 정보 ==="
echo "공통 임시 비밀번호: ${PASSWORD}"
echo "(첫 로그인 후 즉시 변경 안내)"
echo
printf "  %-14s %-35s %s\n" "부서" "이메일" "이름"
printf "  %-14s %-35s %s\n" "----" "------" "----"
for ENTRY in "${USERS[@]}"; do
  IFS='|' read -r DEPT EMAIL NAME <<< "$ENTRY"
  printf "  %-14s %-35s %s\n" "${DEPT}" "${EMAIL}" "${NAME}"
done
printf "  %-14s %-35s %s\n" "admin" "admin@tk101.co.kr" "(기존 관리자 계정 — 별도 등록 없음)"

echo
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "WARN: 일부 계정 등록 실패. 위 로그 확인 필요." >&2
  exit 1
fi
echo "완료."
