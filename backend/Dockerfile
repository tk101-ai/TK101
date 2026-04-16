# TK101 Backend — FastAPI with uv
# ============================================================================
# Multi-stage: builder → runtime
# ============================================================================

FROM python:3.12-slim-bookworm AS builder

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PROJECT_ENVIRONMENT=/venv

WORKDIR /app

# 의존성 먼저 복사 (Docker layer 캐싱)
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev 2>/dev/null || \
    uv sync --no-install-project --no-dev

# 애플리케이션 복사 후 설치
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev 2>/dev/null || uv sync --frozen --no-dev 2>/dev/null || true

# ============================================================================
FROM python:3.12-slim-bookworm AS runtime

# 시스템 의존성 (최소)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv 복사 (dev 편의)
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /bin/

# Non-root 사용자
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# 빌더에서 생성된 venv 복사
COPY --from=builder --chown=app:app /venv /venv
COPY --from=builder --chown=app:app /app /app

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
