#!/usr/bin/env bash
# Tier 1 폴더 (핵심 자료, 약 4,500개) 순차 인덱싱.
# 작은 폴더부터 → PoC 검증 빨리, 문제 빨리 발견.
# 사용: ./scripts/nas-index-tier1.sh
set -uo pipefail

cd "$(dirname "$0")/.."

# 작은 폴더부터 큰 폴더 순. 한 폴더 끝나면 다음 폴더 자동 시작.
TIER1=(
  "TENCENT CLOUD"
  "COMPANY"
  "MARKETING/04_업무 메뉴얼 (★)"
  "MARKETING/00_채널별 소개서 및 견적 가이드"
  "MARKETING/02_TK101 (기존 02. 자료방)"
  "MARKETING/03_공유방"
)

TOTAL=${#TIER1[@]}
i=1
for SUBDIR in "${TIER1[@]}"; do
  echo
  echo "###############################################################"
  echo "# Tier 1 [$i/$TOTAL] $SUBDIR"
  echo "###############################################################"
  ./scripts/nas-index.sh "$SUBDIR" || {
    echo "ERROR: '$SUBDIR' 인덱싱 실패. 다음 폴더로 진행."
  }
  i=$((i + 1))
done

echo
echo "==========================================================="
echo "[Tier 1 완료] 6개 폴더 순차 인덱싱 끝."
echo "다음 단계: ./scripts/nas-index.sh 'MARKETING/01_고객사/<고객사명>' 등으로 Tier 2/3 진행"
echo "==========================================================="
