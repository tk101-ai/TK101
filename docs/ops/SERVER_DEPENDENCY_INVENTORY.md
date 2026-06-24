# 서버 의존성 인벤토리

작성일: 2026-06-23  
범위: `/home/ubuntu/tk101-dev` 메인 앱과 서버 내 외부 폴더, Docker, NAS, GitHub Actions runner 의존성

이 문서는 홈 디렉터리 전체에서 작업하던 기존 흐름을 안전한 branch/worktree 흐름으로
옮기기 위해, repo 밖에 있지만 실제 서비스에 영향을 주는 자원을 분리해 기록한다.

## 한 줄 요약

- Git repo 자체는 `/home/ubuntu/tk101-dev`이지만, 운영은 `/home/ubuntu/actions-runner/_work/TK101/TK101` 체크아웃에서 배포된다.
- Qdrant 데이터는 `/home/ubuntu/qdrant_storage` bind mount에 있으며, 검색 기능의 핵심 운영 데이터다.
- `/home/ubuntu/tk101-rag`는 문서상 별도 파이프라인이지만 현재 Git repo가 아닌 로컬 코드/데이터 묶음이며, `127.0.0.1:8090` 검색 서버가 여기서 실행 중이다.
- NAS는 `/mnt/nas`, `/mnt/nas-rw`, `/mnt/nas-rnd`로 host에 모두 rw mount되어 있다. 컨테이너 안에서는 일부 ro로 재마운트된다.
- `tk101-backend-dev`는 `/home/ubuntu/tk101-dev/backend`를 rw bind mount한다. 따라서 main 작업공간의 backend를 직접 수정하면 dev 컨테이너에 즉시 영향을 줄 수 있다.

## Git 작업공간

| 경로 | 성격 | 현재 상태 | 방침 |
| --- | --- | --- | --- |
| `/home/ubuntu/tk101-dev` | 메인 개발 checkout | `main...origin/main`, untracked `AGENTS.md`, `docs/ops/AI_WORKSPACE_GUARDRAILS.md` | 기준선으로 두고 직접 실험 지양 |
| `/home/ubuntu/worktrees/tk101-codex-safe-workspace` | AI 작업용 worktree | `chore/codex-safe-workspace`, 안전 문서 작업 중 | Codex/Claude 작업 기본 위치 |
| `/home/ubuntu/actions-runner/_work/TK101/TK101` | GitHub Actions 배포 checkout | `main...origin/main`, script 7개 mode만 `100644 -> 100755` 변경 | 운영 checkout. 직접 수정 금지 |

배포 checkout의 script mode 변경은 deploy workflow의 `chmod +x scripts/*.sh` 때문에 생긴 것으로 보인다. 내용 변경은 0줄이다.

## GitHub Actions와 배포

| workflow | trigger | 실행 위치 | 영향 |
| --- | --- | --- | --- |
| `.github/workflows/deploy.yml` | `main` push, 수동 실행 | self-hosted runner | `.env` 생성, `docker compose up -d --build --force-recreate --remove-orphans`, Alembic migration |
| `.github/workflows/e2e.yml` | 수동 실행만 | self-hosted runner | 라이브 `http://43.155.202.112:8080` 대상 Playwright |
| `.github/workflows/backup.yml` | 매일 02:00 KST, 수동 실행 | self-hosted runner | `/mnt/nas-rw/backup/postgres`에 Postgres dump 저장, 7일 초과분 삭제 |

systemd runner:

- service: `actions.runner.tk101-ai-TK101.VM-1-17-ubuntu.service`
- status: active/running
- working directory: `/home/ubuntu/actions-runner`
- exec: `/home/ubuntu/actions-runner/runsvc.sh`

## Docker 서비스와 포트

현재 실행 중인 주요 컨테이너:

| 컨테이너 | 이미지 | 포트 | 비고 |
| --- | --- | --- | --- |
| `tk101-frontend` | `tk101-frontend` | `0.0.0.0:8080 -> 80` | 공개 프론트 |
| `tk101-backend` | `tk101-backend` | `127.0.0.1:8000 -> 8000` | 프론트 nginx가 내부 프록시 |
| `tk101-webui` | `ghcr.io/open-webui/open-webui:main` | `0.0.0.0:3000 -> 8080` | 공개 WebUI |
| `tk101-n8n` | `n8nio/n8n:latest` | `127.0.0.1:5678 -> 5678` | 로컬 바인딩 |
| `tk101-langfuse` | `langfuse/langfuse:2` | `127.0.0.1:3001 -> 3000` | 로컬 바인딩 |
| `tk101-postgres` | `pgvector/pgvector:pg16` | `127.0.0.1:5432 -> 5432` | 운영 DB |
| `tk101-qdrant` | `qdrant/qdrant:latest` | `127.0.0.1:6333-6334` | 검색 DB |
| `tk101-backend-dev` | local image id | `0.0.0.0:8001 -> 8000` | `/home/ubuntu/tk101-dev/backend` rw mount |

추가 host 프로세스:

- Vite dev server: `127.0.0.1:5173`, `/home/ubuntu/tk101-dev/frontend/node_modules/.bin/vite`
- RAG/search server: `127.0.0.1:8090`, cwd `/home/ubuntu/tk101-rag`

## Docker mounts

| 컨테이너 | host/source | container target | mode | 의미 |
| --- | --- | --- | --- | --- |
| `tk101-postgres` | `tk101_postgres_data` | `/var/lib/postgresql/data` | rw | 운영 DB 데이터 |
| `tk101-postgres` | `/home/ubuntu/actions-runner/_work/TK101/TK101/infra/init-db.sql` | `/docker-entrypoint-initdb.d/init-db.sql` | ro | 배포 checkout 파일 참조 |
| `tk101-n8n` | `tk101_n8n_data` | `/home/node/.n8n` | rw | n8n 데이터 |
| `tk101-webui` | `tk101_webui_data` | `/app/backend/data` | rw | Open WebUI 데이터 |
| `tk101-qdrant` | `/home/ubuntu/qdrant_storage` | `/qdrant/storage` | rw | Qdrant docs_text 등 검색 데이터 |
| `tk101-backend` | `/mnt/nas-rw` | `/mnt/nas-rw` | rw | 문서 생성물/로그/첨부 저장 |
| `tk101-backend` | `/mnt/nas` | `/mnt/nas` | ro | NAS 읽기 |
| `tk101-backend` | `/mnt/nas-rnd` | `/mnt/nas-rnd` | ro | RND NAS 읽기 |
| `tk101-backend` | `tk101_hf_cache` | `/root/.cache/huggingface` | rw | 모델 캐시 |
| `tk101-backend` | `tk101_form_filler_data` | `/var/lib/form_filler` | rw | 문서작업 산출/업로드 |
| `tk101-backend` | `tk101_distribution_telethon_data` | `/var/lib/distribution` | rw | Telethon 세션 |
| `tk101-backend` | `/home/ubuntu/actions-runner/_work/TK101/TK101/.local` | `/srv/.local` | rw | 로컬 credential drop 위치 |
| `tk101-backend` | `tk101_playground_media` | `/var/lib/playground/media` | rw | Playground 미디어 |
| `tk101-backend-dev` | `/home/ubuntu/tk101-dev/backend` | `/srv` | rw | main checkout backend 직접 반영 |

Docker named volumes:

- `tk101_postgres_data`
- `tk101_n8n_data`
- `tk101_webui_data`
- `tk101_hf_cache`
- `tk101_form_filler_data`
- `tk101_distribution_telethon_data`
- `tk101_playground_media`

Docker 사용량 기준:

- Images: 108.3GB, reclaimable 65.24GB
- Containers: 7.955GB
- Local volumes: 13.91GB
- Build cache: 24.48GB, reclaimable 24.39GB

주의: reclaimable 용량이 크더라도 `docker system prune`, `docker image prune`,
`docker builder prune`, `docker compose down -v`는 owner 승인 전 금지한다.

## NAS mounts

`/etc/fstab`에 sshfs mount가 등록되어 있다.

| mount | remote | host mode | container mode |
| --- | --- | --- | --- |
| `/mnt/nas` | `TK101GLOBAL` | rw | backend에서는 ro |
| `/mnt/nas-rw` | `TK101AI` | rw | backend에서는 rw |
| `/mnt/nas-rnd` | `TK101_RND` | rw | backend에서는 ro |

현재 NAS 파일시스템 사용량:

- 용량 35T, 사용 21T, 여유 15T, 사용률 59%

주의: host에서는 세 mount 모두 rw다. 작업자가 host에서 직접 쓰거나 삭제하면 컨테이너의 ro 설정과 무관하게 운영 데이터에 영향을 줄 수 있다.

## 외부 RAG/Search 파이프라인

경로: `/home/ubuntu/tk101-rag`

현재 상태:

- Git repo 아님. `.git` 없음.
- 크기: 약 7.0GB
- 주요 하위 크기:
  - `data`: 5.6GB
  - `.venv`: 1.4GB
  - `logs`: 1.1MB
- `127.0.0.1:8090`에서 `app.server:app` uvicorn 실행 중
- 실행 cwd: `/home/ubuntu/tk101-rag`
- 실행 스크립트: `run_search_server.sh`
- `.search.env` 존재. 내용 출력 금지.

역할:

- NAS 문서 파싱/청킹/임베딩/Qdrant 적재 파이프라인
- Qdrant `docs_text` 2560-dim 컬렉션과 payload 스키마의 기준
- 문서 임베딩은 RunPod/vLLM API를 사용하도록 설계되어 있음
- 라이브 쿼리 임베딩은 로컬 CPU 모델을 사용할 수 있도록 구성되어 있음

주의:

- Git 이력이 없으므로 변경 추적/rollback이 약하다.
- `.search.env`, `.venv`, `data`, `logs`를 무심코 복사/삭제하지 않는다.
- 검색 품질이나 Qdrant schema 변경 작업은 메인 앱 변경과 별도 작업으로 취급한다.

## repo 내부 외부경로 참조

주요 참조 위치:

- `docker-compose.yml`
  - `/home/ubuntu/qdrant_storage:/qdrant/storage`
  - `/mnt/nas`, `/mnt/nas-rw`, `/mnt/nas-rnd`
  - `QDRANT_URL`, `NAS_MOUNT_PATH`
- `backend/app/config.py`
  - `nas_mount_path=/mnt/nas`
  - `qdrant_url=http://qdrant:6333`
  - `docwork_nas_output_root=/mnt/nas-rw/문서작업`
  - `playground_log_path=/mnt/nas-rw/logs/backend/backend.log`
  - `distribution_attachment_dir=/mnt/nas-rw/distribution/attachments`
- `.github/workflows/deploy.yml`
  - `main` push 배포
  - runner checkout에서 `.env` 생성
  - `docker compose up -d --build --force-recreate --remove-orphans`
  - Alembic migration 자동 실행
- `.github/workflows/backup.yml`
  - `/mnt/nas-rw/backup/postgres`에 DB backup
  - 7일 초과 `*.sql.gz` 삭제
- `scripts/README.md`, `scripts/healthcheck.sh`
  - `/home/ubuntu/actions-runner/_work/TK101/TK101`에서 실행 전제
  - Docker, NAS, API, 로그 확인

## 자동 실행/스케줄

- ubuntu 사용자 crontab: 없음
- system cron: TK101 전용으로 보이는 항목 없음. 기본 `sysstat`, `logrotate`, `apt`, Tencent agent cron 등 존재
- GitHub Actions backup workflow: 매일 02:00 KST
- GitHub Actions runner service: active/running

## 위험 구역

명시 승인 없이 변경하지 않는다.

- `/home/ubuntu/qdrant_storage`
- `/home/ubuntu/actions-runner`
- `/home/ubuntu/actions-runner/_work/TK101/TK101/.env`
- `/home/ubuntu/actions-runner/_work/TK101/TK101/.local`
- `/home/ubuntu/tk101-rag`
- `/mnt/nas`, `/mnt/nas-rw`, `/mnt/nas-rnd`
- Docker named volumes
- Postgres/Qdrant 데이터
- GitHub Actions runner service
- `main` push 또는 merge

## 작업 전 검증 루틴

일반 코드 작업:

```bash
git -C /home/ubuntu/worktrees/<worktree> status --short --branch
git -C /home/ubuntu/worktrees/<worktree> diff --stat
```

외부 자원 관련 작업 전:

```bash
rg -n '(/home/ubuntu|/mnt/nas|qdrant|actions-runner|tk101-rag)' /home/ubuntu/worktrees/<worktree>
docker ps -a
docker inspect tk101-backend tk101-qdrant --format '{{.Name}} {{json .Mounts}}'
ss -ltnp
df -h / /mnt/nas /mnt/nas-rw /mnt/nas-rnd
```

배포 전:

```bash
git -C /home/ubuntu/actions-runner/_work/TK101/TK101 status --short --branch
git -C /home/ubuntu/tk101-dev status --short --branch
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

주의: 위 명령은 읽기 전용 점검용이다. `docker compose up`, `docker compose down`,
`docker prune`, `rm`, `pkill`, migration 실행은 별도 승인 후에만 한다.

## 현재 남은 확인 과제

- `/home/ubuntu/tk101-rag`를 Git repo로 승격할지, 별도 백업/스냅샷 대상으로 둘지 결정.
- `tk101-backend-dev`가 계속 필요한지 확인. 필요하다면 main checkout 대신 별도 worktree를 mount하도록 재구성 검토.
- Vite dev server가 `/home/ubuntu/tk101-dev/frontend`에서 계속 실행 중인 이유 확인.
- runner checkout의 script mode 변경을 repo에 반영할지, workflow에서 checkout마다 생기는 dirty 상태로 둘지 결정.
- PR 검증 workflow를 추가해 `main` merge 전 frontend build/backend checks를 자동화.
- `main` push 자동 배포를 유지할지, 수동 승인 배포로 바꿀지 결정.

