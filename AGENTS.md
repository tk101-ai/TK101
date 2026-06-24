# TK101 Codex instructions

Use this file as the Codex equivalent of `CLAUDE.md`. The historical Claude Code instructions remain in `CLAUDE.md`; when this file and `CLAUDE.md` differ, follow this file plus the user's latest message.

Core workflow:
- Primary backlog: `docs/BACKLOG.md`.
- AI workspace safety guide: `docs/ops/AI_WORKSPACE_GUARDRAILS.md`.
- Server dependency inventory: `docs/ops/SERVER_DEPENDENCY_INVENTORY.md`.
- Recent context: `docs/worklogs/`, especially the latest dated file.
- Design/review references: `docs/prd/`, `docs/reviews/`, `docs/ops/`, and `docs/decisions/`.
- Before substantive code changes, inspect the relevant code and docs rather than assuming.

Autonomy and approval:
- Proceed autonomously for ordinary code, docs, tests, and server configuration work.
- Ask first for destructive production changes, permanent data/file deletion, DROP or irreversible migrations, large embedding/LLM jobs, cloud console or firewall/security-group changes, external account/password work, and other high-cost actions.

Technical conventions:
- Use branches and PRs for normal repository changes; do not push directly to `main`.
- Keep `main` as the stable baseline. Prefer isolated git worktrees under `/home/ubuntu/worktrees/*` for AI-assisted implementation.
- Frontend verification must use `npm run build` from `frontend` because it runs `tsc -b && vite build`.
- Backend verification should include Python compile/import checks and targeted tests where applicable.
- For DB migrations, test on the dev DB/container before production deployment.
- After deploy, verify the running production behavior before reporting work as complete.
- UI copy should be Korean.
- Avoid hardcoding accounts, brands, departments, platforms, or Seoul-specific assumptions; use DB/corpus-driven iteration.

Stack and operations:
- Frontend: React 19, antd v6, recharts 2.x, Vite.
- Backend: FastAPI, SQLAlchemy async, Alembic.
- Deploy path: merge to `main` triggers the self-hosted runner and `docker compose up -d --build`, then Alembic in container.
- Main containers include `tk101-backend`, `tk101-backend-dev`, `tk101-postgres`, `tk101-qdrant`, and `tk101-frontend`.
- Search source of truth: Qdrant `docs_text` using Qwen3 2560d embeddings. In-app pgvector/indexer paths were removed; external pipeline lives in `/home/ubuntu/tk101-rag`.

High-value references:
- `docs/BACKLOG.md`: current queue and owner-approval items.
- `docs/worklogs/2026-06-23.md`: latest remediation and deployment state.
- `docs/reviews/CODE_REVIEW_FULL_2026-06-22.md`: quality/security follow-up background.
- `docs/reviews/REVIEW_SECURITY_DOMAIN_CLEANUP_2026-06-22.md`: security, domain, and cleanup plan.
- `/home/ubuntu/tk101-rag/TK101_작업현황_인수인계_v2.md`: NAS/RAG handoff context.

Safety notes:
- Do not expose `.env`, credentials, auth caches, SSH keys, NAS keys, or token values in chat.
- Treat `/home/ubuntu/qdrant_storage`, `/home/ubuntu/actions-runner`, `/home/ubuntu/tk101-rag`, Docker volumes, Postgres data, and NAS mounts as production-adjacent.
- Do not run Docker prune, `docker compose down -v`, irreversible DB operations, NAS write/delete operations, or runner changes unless the owner explicitly approves.
- Respect the backlog markers: `⚠️오너승인`, `⚠️비용`, `⚠️대형/논의`, and `⚠️영향큼`.
