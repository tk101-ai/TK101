# TK101 AI Platform

> 사내 40명 대상 AI 업무 자동화 플랫폼. 1인 담당자(TK101) + Claude Code 기반 개발.

## 문서 진입점

- **프로젝트 헌법**: [CLAUDE.md](CLAUDE.md) ← 모든 작업 전 먼저 확인
- **현재 feature Plan**: [docs/01-plan/features/tk101-platform-foundation.plan.md](docs/01-plan/features/tk101-platform-foundation.plan.md)
- **현재 feature Design**: [docs/02-design/features/tk101-platform-foundation.design.md](docs/02-design/features/tk101-platform-foundation.design.md)

## 빠른 시작 (Sprint 0 완료 후)

```bash
# 1. 환경변수 준비
cp .env.example .env
# .env 내 값들 실제 환경에 맞게 수정

# 2. 전체 스택 기동
docker compose up -d

# 3. 접속
# - Frontend: http://localhost:3000
# - Backend:  http://localhost:8000
# - Health:   http://localhost:8000/health
# - API Docs: http://localhost:8000/docs
```

## 기술 스택

- **Backend**: FastAPI (Python 3.12+), SQLAlchemy 2.0 async, Alembic
- **Frontend**: Next.js 15 (App Router, TypeScript), Tailwind + shadcn/ui
- **DB**: PostgreSQL 16 + Redis
- **인증**: JWT (HS256) + bcrypt
- **배포**: Docker Compose + GitHub Actions → Tencent CVM
- **아키텍처**: Clean Architecture (4 레이어)

자세한 설계는 [Design 문서](docs/02-design/features/tk101-platform-foundation.design.md) 참조.

## 디렉터리 구조

```
TK101 AI/
├── backend/         # FastAPI (Clean Architecture 4 레이어)
├── frontend/        # Next.js (Features + layered imports)
├── docs/            # PDCA 문서 (01-plan, 02-design, ...)
├── docker-compose.yml
├── .github/workflows/deploy.yml
├── CLAUDE.md        # 프로젝트 헌법 (세션 자동 로드)
└── .claude/rules/   # ECC + 프로젝트 규칙
```

## 개발 플로우

`CLAUDE.md §3` 라우팅 테이블 참조. 기능 개발은 13단계 표준 플로우를 따름:

1. `/bkit:pdca plan <feature>` (bkit)
2. `/bkit:pdca design <feature>` (bkit, Clean Architecture 선택)
3. `/plan` + `/tdd` (ECC, 테스트 먼저)
4. 코드 작성 (ECC 자동 리뷰어)
5. `/bkit:pdca analyze → iterate → qa → report` (bkit)
6. `git push` → 자동 배포

## 현재 상태

[.claude/rules/project/current-status.md](.claude/rules/project/current-status.md) 참조.

## License

Private — TK101 Global Korea Inc.
