#!/usr/bin/env bash
# v0.6.x NAS 검색 PoC 라이브 헬스체크. 한 번에 다 출력.
# 사용: ./scripts/healthcheck.sh
set -uo pipefail

cd "$(dirname "$0")/.."

echo "=== git ==="
git log --oneline -1

echo
echo "=== 컨테이너 상태 ==="
sudo docker compose ps backend

echo
echo "=== 이미지 사이즈 ==="
sudo docker images tk101-backend --format '{{.Repository}}:{{.Tag}}  {{.Size}}  ({{.CreatedSince}})'

echo
echo "=== 코드 패치 검증 ==="
sudo docker compose exec -T backend bash -c '
  echo "EXCLUDED_DIR_NAMES: $(grep -c EXCLUDED_DIR_NAMES app/services/nas_search/file_walker.py)"
  echo "_resolve_scan_root: $(grep -c _resolve_scan_root app/services/nas_search/indexer.py)"
  echo "subdir 스키마:      $(grep -c subdir app/schemas/nas_file.py)"
  echo "asyncio.to_thread:  $(grep -c asyncio.to_thread app/services/nas_search/indexer.py)"
  echo "torch (CPU/CUDA):   $(python -c "import torch; print(torch.__version__, torch.cuda.is_available())")"
'

echo
echo "=== NAS 마운트 (컨테이너 내부) ==="
sudo docker compose exec -T backend bash -c '
  echo "NAS_MOUNT_PATH=$NAS_MOUNT_PATH"
  ls /mnt/nas | head -5
'

echo
echo "=== API 헬스 (401 정상) ==="
curl -s -o /dev/null -w "GET /api/nas/status: %{http_code}\n" http://localhost:8000/api/nas/status
curl -s -o /dev/null -w "GET /api/auth/me:    %{http_code}\n" http://localhost:8000/api/auth/me

echo
echo "=== 호스트 디스크 ==="
df -h / | tail -1

echo
echo "=== backend 로그 (마지막 10줄) ==="
sudo docker compose logs --tail 10 backend

echo
echo "=== 헬스체크 종료 ==="
