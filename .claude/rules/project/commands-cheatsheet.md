# 자주 쓰는 명령어 치트시트

> CLAUDE.md에서 참조. 명령어 기억 안 날 때 이 파일을 여세요.

## 프로젝트 상태 확인

```bash
/bkit:pdca status                    # 현재 PDCA 상태
/bkit:pdca next                      # 다음 단계 가이드
/bkit:skill-status                   # 로드된 스킬 확인
git status
git log --oneline -5
docker compose ps                    # 컨테이너 상태 (서버 기동 후)
```

## 개발 서버 실행 (Sprint 0 완료 후)

### 전체 스택 (Docker Compose)

```bash
docker compose up -d                 # 백그라운드 기동
docker compose logs -f backend       # 백엔드 로그 스트리밍
docker compose logs -f frontend      # 프론트 로그
docker compose down                  # 전체 중지
```

### 개별 서비스 (개발 시)

```bash
# 백엔드
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프론트
cd frontend
pnpm dev
```

## 테스트

```bash
# 백엔드 전체 테스트 + 커버리지
cd backend
uv run pytest --cov=app --cov-report=term-missing

# 특정 레이어만
uv run pytest tests/unit/domain/          # Domain 단위
uv run pytest tests/integration/          # Infrastructure + API
uv run pytest tests/e2e/                  # E2E

# 프론트 E2E
cd frontend
pnpm playwright test
pnpm playwright test --ui                 # UI 모드
```

## DB 마이그레이션 (Alembic)

```bash
cd backend

# 새 마이그레이션 생성
uv run alembic revision --autogenerate -m "add user table"

# 적용
uv run alembic upgrade head

# 롤백 (주의)
uv run alembic downgrade -1

# 히스토리 확인
uv run alembic history
```

## 시드 데이터

```bash
cd backend
uv run python scripts/seed.py
```

## PDCA 사이클

```bash
/bkit:pdca plan <feature>            # 새 기능 기획
/bkit:pdca design <feature>          # 설계 (아키텍처 옵션 선택)
/bkit:pdca do <feature>              # 구현 가이드 (전체)
/bkit:pdca do <feature> --scope X    # 구현 가이드 (특정 모듈만)
/bkit:pdca analyze <feature>         # 갭 분석 (90% 목표)
/bkit:pdca iterate <feature>         # 자동 개선 (갭 < 90% 시)
/bkit:pdca qa <feature>              # QA 단계
/bkit:pdca report <feature>          # 완료 보고서
/bkit:pdca archive <feature>         # 문서 아카이브
/bkit:pdca status                    # 현재 상태
/bkit:pdca next                      # 다음 단계 추천
```

## bkit Phase 명령어

```bash
/bkit:phase-1-schema                 # DB 스키마 공식화
/bkit:phase-2-convention             # 코딩 컨벤션 공식화
/bkit:phase-3-mockup                 # UI 목업
/bkit:phase-6-ui-integration         # 프론트 UI + API 연동
/bkit:phase-8-review                 # 최종 품질 검증
/bkit:qa-phase                       # L1-L5 QA 테스트
/bkit:deploy                         # 배포 실행
```

## ECC 슬래시 명령어

```bash
/plan                                # 구현 계획 수립
/tdd                                 # TDD 시작 (테스트 먼저)
/code-review                         # 로컬 변경사항 리뷰
/build-fix                           # 빌드 에러 해결
/verify                              # 검증 루프
/refactor-clean                      # 리팩토링 정리
```

## ECC 에이전트 직접 호출 (Claude가 자동으로 쓰는 경우가 많음)

| 에이전트 | 호출 시점 |
|---------|---------|
| `python-reviewer` | Python 파일 저장 시 자동 |
| `typescript-reviewer` | TS/TSX 파일 저장 시 자동 |
| `database-reviewer` | DB 관련 작업 시 수동 |
| `security-reviewer` | 인증/보안 코드 작성 시 필수 (수동) |
| `architect` | 복잡한 시스템 설계 시 |
| `planner` | `/plan` 커맨드가 호출 |
| `tdd-guide` | `/tdd` 커맨드가 호출 |
| `build-error-resolver` | `/build-fix` 또는 빌드 실패 시 |
| `e2e-runner` | E2E 테스트 작성/실행 시 |
| `gap-detector` | `/bkit:pdca analyze`가 호출 |
| `code-reviewer` | PR 직전 수동 호출 가능 |

## Git 워크플로우

```bash
# 작업 시작 시 브랜치 생성 (큰 기능)
git checkout -b feature/<feature-name>

# 커밋 (conventional commits)
git add .
git commit -m "feat: add user authentication"
git commit -m "fix: handle expired refresh token"
git commit -m "refactor: extract auth use case"
git commit -m "test: add domain unit tests for user"
git commit -m "docs: update API documentation"

# PR 생성 (main 브랜치로)
gh pr create --title "feat: user authentication" --body "..."

# main 직접 푸시 (작은 수정)
git checkout main
git push
```

## Docker 명령어 (디버깅 시)

```bash
# 특정 서비스 재시작
docker compose restart backend

# 컨테이너 쉘 진입
docker compose exec backend bash
docker compose exec postgres psql -U postgres

# 볼륨 초기화 (주의: DB 데이터 삭제)
docker compose down -v

# 이미지 재빌드
docker compose build --no-cache backend
```

## Tencent CVM 배포 확인 (GitHub Actions가 자동 실행)

```bash
# 로컬에서 서버 접속
ssh -i ~/.ssh/tk101_cvm user@<cvm-ip>

# 서버에서 상태 확인
docker compose ps
docker compose logs -f
```
