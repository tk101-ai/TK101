# AI 작업공간 안전 운용 가이드

이 문서는 TK101 서버에서 Claude Code, Codex, 기타 AI 에이전트가 작업할 때
건드려도 되는 영역과 반드시 보호해야 하는 운영 자원을 구분하기 위한 기준선이다.

## 기본 원칙

- `/home/ubuntu/tk101-dev`는 메인 코드 저장소다.
- `main`은 안정 기준선으로 둔다.
- 일반 코드/문서 작업은 별도 branch 또는 git worktree에서 진행한다.
- 운영 데이터, 배포 runner, Docker volume, NAS mount는 명시 승인 없이는 변경하지 않는다.
- 삭제, prune, migration, 배포, 대형 임베딩/LLM 작업은 반드시 owner 승인 후 진행한다.

## Git과 배포 트리거

- remote: `https://github.com/tk101-ai/TK101`
- deploy workflow: `.github/workflows/deploy.yml`
- 자동 배포 조건: `main` 브랜치 push
- 수동 배포 조건: `workflow_dispatch`
- E2E workflow: `.github/workflows/e2e.yml`, 현재 수동 실행만 사용
- backup workflow: **제거됨(2026-06-24)** — 현재 자동 DB 백업 없음 (필요 시 신규 구성)

따라서 feature/fix/docs 브랜치에서 로컬 작업하거나 PR용 브랜치를 push하는 것은
자동 배포를 직접 트리거하지 않는다. 단, `main`에 merge 또는 push되면 self-hosted
runner가 실제 서버에서 `docker compose up -d --build --force-recreate --remove-orphans`
와 Alembic migration을 실행한다.

## 작업 영역 구분

| 경로 | 성격 | 위험도 | 방침 |
| --- | --- | --- | --- |
| `/home/ubuntu/tk101-dev` | 메인 코드 저장소 | 중 | `main` 기준선. 직접 실험보다 branch/worktree 권장 |
| `/home/ubuntu/worktrees/*` | AI/작업자별 격리 작업공간 | 낮음 | 일반 기능/문서/수정 작업 기본 위치 |
| `/home/ubuntu/tk101-rag` | NAS/RAG 외부 파이프라인 | 중~높음 | 메인 앱과 별도 repo/운영 파이프라인으로 취급 |
| `/home/ubuntu/qdrant_storage` | Qdrant 검색 DB bind mount | 높음 | 삭제/이동/초기화 금지 |
| `/home/ubuntu/actions-runner` | GitHub Actions self-hosted runner | 높음 | runner 설정/파일 변경 금지 |
| `/home/ubuntu/pg_backups` | DB 백업 | 높음 | 보존. 정리 전 owner 승인 |
| `/mnt/nas`, `/mnt/nas-rw`, `/mnt/nas-rnd` | NAS mount | 높음 | 코드 작업 중 직접 쓰기 금지 |
| Docker volumes | Postgres, n8n, webui, langfuse 등 운영 데이터 | 높음 | prune/remove/down -v 금지 |
| `/home/ubuntu/tk101-dev-nas` | 낡은 repo 사본으로 문서상 표시 | 중 | 삭제 전 최종 확인 및 owner 승인 |

## 기본 작업 절차

1. `git status --short --branch`로 시작 상태를 확인한다.
2. 작업 단위마다 새 branch 또는 worktree를 만든다.
3. 관련 문서와 코드만 읽고 변경한다.
4. `git diff --stat`과 `git diff`로 변경 범위를 확인한다.
5. 가능한 범위에서 build/test/lint를 실행한다.
6. 결과를 요약하고, 배포가 필요한 경우 `main` merge 전에 owner에게 확인한다.

## 권장 worktree 예시

```bash
mkdir -p /home/ubuntu/worktrees
git -C /home/ubuntu/tk101-dev worktree add -b docs/example-task /home/ubuntu/worktrees/tk101-example-task main
```

작업자는 VS Code에서 해당 worktree 폴더를 별도로 열어도 된다.

## AI 에이전트 금지선

명시 승인 없이 다음을 실행하지 않는다.

- `docker compose down -v`
- `docker system prune`, `docker image prune`, `docker builder prune`
- `/home/ubuntu/qdrant_storage` 삭제/이동/권한 변경
- `/mnt/nas*` 대량 쓰기/삭제
- Postgres `DROP`, truncate, irreversible migration
- GitHub Actions runner 재설정
- secret, token, SSH key, `.env` 내용 출력
- `main` 직접 push

## 추천 역할 분리

- VS Code: 파일 탐색, 직접 확인, diff 검토
- Claude Code: 익숙한 구현 작업
- Codex: 구조 파악, 안전 점검, 리뷰, worktree 기반 작업, 검증 루틴
- Git branch/worktree: 작업 경계

