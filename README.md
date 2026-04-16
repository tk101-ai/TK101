# TK101 AI

사내 AI 자동화 인프라. Walking Skeleton 단계 — `/health` 엔드포인트와 CI/CD 파이프라인만 존재.

## 프로젝트 구조

```
├── backend/                 # FastAPI 앱
│   ├── app/main.py          # /health 엔드포인트
│   ├── pyproject.toml       # 의존성 + ruff 설정
│   └── Dockerfile           # 런타임 이미지
├── docker-compose.yml       # 서비스 정의
└── .github/workflows/
    └── deploy.yml           # main push → self-hosted runner 배포
```

## 배포 흐름

1. 로컬에서 변경 → `git push origin main`
2. GitHub이 self-hosted runner(CVM: `VM-1-17-ubuntu`)에 작업 전달
3. Runner가 `ruff check` + `ruff format --check` 통과 확인
4. `docker compose up -d --build` 로 컨테이너 재빌드/재시작
5. `http://<CVM_IP>:8000/health` 로 확인

## 로컬 개발

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload
```

## 사전 요구사항

- CVM에 GitHub Actions self-hosted runner 등록 (systemd service)
- CVM 보안 그룹에서 8000 포트 인바운드 허용
- CVM의 `ubuntu` 사용자가 `docker` 그룹 포함

## 커밋 규약

모든 커밋은 `<type>(<scope>): <subject>` 형식을 따른다.
상세: [`docs/COMMIT_CONVENTION.md`](docs/COMMIT_CONVENTION.md)

```bash
# 템플릿 활성화 (1회)
git config --local commit.template .gitmessage
```
