# 커밋 규약

커밋 메시지는 **Conventional Commits** 형식을 따른다. 어떤 종류의 작업을 어느 영역에 했는지 한 줄로 바로 알 수 있어야 한다.

## 기본 형식

```
<type>(<scope>): <subject>

<body (선택)>
```

- **subject**: 명령형, 50자 이내, 마침표 없음
- **body**: 왜 변경했는지, 영향은 무엇인지 (선택)
- **scope**: 영향 영역 (선택이지만 가능하면 기입)

## 타입 (라벨)

| 타입 | 의미 | 예시 |
|---|---|---|
| `feat` | 새로운 기능 | `feat(backend): add user login endpoint` |
| `fix` | 버그 수정 | `fix(backend): handle empty payload in /health` |
| `refactor` | 동작 변경 없는 코드 개선 | `refactor(backend): extract config loader` |
| `build` | 빌드/패키징 (Dockerfile, pyproject 등) | `build(backend): pin fastapi to 0.115` |
| `ci` | CI/CD 파이프라인 | `ci: add smoke test after deploy` |
| `docs` | 문서만 변경 | `docs: update README deployment flow` |
| `test` | 테스트 추가/수정 | `test(backend): add /health integration test` |
| `chore` | 기타 유지보수 | `chore: add .gitignore entries for .venv` |
| `perf` | 성능 개선 | `perf(backend): cache DB session factory` |
| `style` | 포맷/린트만 변경 (동작 동일) | `style: apply ruff format` |

## 스코프 예시

- `backend` — FastAPI 앱 코드
- `ci` — GitHub Actions, 배포 스크립트
- `docker` — Dockerfile, docker-compose
- `docs` — 문서
- `root` — 프로젝트 루트 설정 (.gitignore 등)

스코프가 불분명하거나 여러 영역에 걸치면 생략 가능.

## 실제 예시

```
feat(backend): add FastAPI /health endpoint

- GET /health → {"status":"ok"}
- Walking Skeleton 단계: 배포 파이프라인 검증용 최소 엔드포인트
```

```
ci: add deploy workflow for self-hosted runner

main 브랜치 push 시:
1. ruff check + ruff format --check
2. docker compose up -d --build
```

```
chore: add .gitignore and .dockerignore
```

## 한 커밋에 여러 파일을 묶을 때

논리적으로 하나의 변경이면 묶는다. 성격이 다르면 분리한다.

- O: `backend/Dockerfile` + `docker-compose.yml` → 둘 다 패키징/실행 → `build: add container setup`
- X: `backend/app/main.py` + `.github/workflows/deploy.yml` → 앱 변경과 CI 변경은 분리

## 템플릿 활성화 (선택)

루트에 `.gitmessage` 파일이 있다. 한 번만 설정하면 `git commit` 시 자동으로 형식이 뜬다.

```bash
git config --local commit.template .gitmessage
```

이후 `git commit` (메시지 옵션 없이) 실행하면 에디터에 템플릿과 라벨 가이드가 함께 보인다.
