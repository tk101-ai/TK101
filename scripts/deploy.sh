#!/usr/bin/env bash
# ============================================================================
# TK101 AI Platform — CVM Deploy Script
# ============================================================================
# GitHub Actions에서 SSH로 호출됨.
# 실행 위치: CVM의 /opt/tk101/
#
# 흐름:
#   1. 기존 컨테이너 정지
#   2. 이미지 재빌드
#   3. 컨테이너 기동
#   4. 헬스체크 (3회 재시도)
#   5. 실패 시 로그 출력
# ============================================================================

set -euo pipefail

# ─────────── 색상 출력 ───────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─────────── 사전 검증 ───────────
if [[ ! -f .env ]]; then
    log_error ".env 파일이 없습니다. GitHub Actions에서 업로드되어야 합니다."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    log_error "Docker가 설치되어 있지 않습니다."
    log_error "CVM 초기 세팅 가이드 참조: docs/deployment/cvm-initial-setup.md"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    log_error "Docker Compose가 설치되어 있지 않습니다."
    exit 1
fi

# ─────────── 배포 시작 ───────────
log_info "TK101 AI Platform 배포 시작"
log_info "현재 디렉터리: $(pwd)"
log_info "git commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'N/A')"

COMPOSE_FILE="docker-compose.prod.yml"
if [[ ! -f $COMPOSE_FILE ]]; then
    log_warn "$COMPOSE_FILE 없음, docker-compose.yml 사용"
    COMPOSE_FILE="docker-compose.yml"
fi

log_info "사용할 compose 파일: $COMPOSE_FILE"

# ─────────── 1. 기존 컨테이너 정지 ───────────
log_info "[1/4] 기존 컨테이너 정지"
docker compose -f "$COMPOSE_FILE" down --remove-orphans || true

# ─────────── 2. 이미지 재빌드 ───────────
log_info "[2/4] 이미지 재빌드 (5~10분 소요)"
docker compose -f "$COMPOSE_FILE" build --pull

# ─────────── 3. 컨테이너 기동 ───────────
log_info "[3/4] 컨테이너 기동"
docker compose -f "$COMPOSE_FILE" up -d

# ─────────── 4. 헬스체크 ───────────
log_info "[4/4] 헬스체크"
sleep 8

HEALTH_OK=0
for i in 1 2 3 4 5; do
    log_info "  헬스체크 시도 $i/5..."
    if curl -fsS http://localhost:8000/health | grep -q '"status":"ok"'; then
        log_info "  ✅ Backend /health OK"
        HEALTH_OK=1
        break
    fi
    sleep 6
done

if [[ $HEALTH_OK -eq 0 ]]; then
    log_error "Backend 헬스체크 실패"
    log_error "최근 로그 (backend):"
    docker compose -f "$COMPOSE_FILE" logs --tail=50 backend
    exit 1
fi

# Frontend는 Next.js SSR 기동에 시간 걸릴 수 있으므로 경고만
if curl -fsS -o /dev/null http://localhost:3000; then
    log_info "  ✅ Frontend OK"
else
    log_warn "  ⚠️ Frontend가 아직 준비되지 않음 (정상일 수 있음, 30초 후 재확인 필요)"
fi

# ─────────── 정리 ───────────
log_info "사용하지 않는 Docker 리소스 정리"
docker image prune -f --filter "until=72h" || true

log_info "🎉 배포 완료"
log_info "  Backend:  http://$(curl -s ifconfig.me 2>/dev/null || echo 'CVM'):8000"
log_info "  Frontend: http://$(curl -s ifconfig.me 2>/dev/null || echo 'CVM'):3000"
log_info "  Health:   http://$(curl -s ifconfig.me 2>/dev/null || echo 'CVM'):8000/health"
