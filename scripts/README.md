# scripts/

라이브 서버 운영용 스크립트 모음. 모두 `/home/ubuntu/actions-runner/_work/TK101/TK101`에서 실행.

## 헬스체크

```bash
./scripts/healthcheck.sh
```

git 커밋, 컨테이너, 이미지 사이즈, 코드 패치, NAS 마운트, API 헬스, 디스크, backend 로그를 한 번에 출력. 자동 배포 후 또는 의심스러울 때.

## NAS 인덱싱 (단일 폴더)

```bash
# 폴더 지정 (subdir은 NAS_MOUNT_PATH 기준 상대 경로)
./scripts/nas-index.sh "TENCENT CLOUD"
./scripts/nas-index.sh "MARKETING/04_업무 메뉴얼 (★)"

# 전체 (NAS 11만 파일 기준 며칠 걸림 — 권장 X)
./scripts/nas-index.sh

# 강제 재인덱싱 (기존 vector 삭제 후 다시)
./scripts/nas-index.sh --full "TENCENT CLOUD"
```

- admin 토큰 자동 발급 (admin@tk101.co.kr)
- POST /api/nas/index/run 호출
- 60초마다 진행률 폴링 → 인덱싱 종료까지 기다림
- 끝나면 최종 status JSON 출력

## NAS 인덱싱 (Tier 1 일괄)

```bash
./scripts/nas-index-tier1.sh
```

핵심 폴더 6개 순차 자동 인덱싱:
1. TENCENT CLOUD (583)
2. COMPANY (2,007)
3. MARKETING/04_업무 메뉴얼 (★) (620)
4. MARKETING/00_채널별 소개서 및 견적 가이드 (415)
5. MARKETING/02_TK101 (488)
6. MARKETING/03_공유방 (461)

총 약 4,500개. 한 폴더 끝나면 다음 자동 시작. 한 폴더 실패해도 다음 진행.

## admin 토큰 (다른 스크립트에서 활용)

```bash
TOKEN=$(./scripts/admin-token.sh)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/me
```

env로 오버라이드:
```bash
ADMIN_EMAIL=other@tk101.co.kr ADMIN_PASSWORD=xxx ./scripts/admin-token.sh
```

## 사용 예시 (가장 흔한 흐름)

```bash
# 1. push 후 자동 배포 끝났는지 + 코드 적용됐는지 확인
./scripts/healthcheck.sh

# 2. 우선순위 폴더 일괄 인덱싱 (백그라운드로 두고 다른 일 가능)
nohup ./scripts/nas-index-tier1.sh > /tmp/tier1.log 2>&1 &
tail -f /tmp/tier1.log    # 보고 싶을 때만

# 3. 끝났으면 사이트에서 검색 테스트
```
