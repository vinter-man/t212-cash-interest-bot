FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

# The container runs with a read-only filesystem, so bytecode is compiled at build time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# Dependencies first, so a code change does not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

# README.md is package metadata (pyproject `readme`), needed only to build the project itself.
COPY README.md ./
COPY cash_interest ./cash_interest
RUN uv sync --frozen --no-dev --no-editable --no-cache \
    && rm -rf cash_interest

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

RUN useradd --system --uid 10001 --no-create-home bot \
    && mkdir -p /app/data \
    && chown bot /app/data
USER bot

ENV DB_PATH=/app/data/cash-interest.db \
    HEARTBEAT_FILE=/tmp/cash-interest.heartbeat \
    MPLCONFIGDIR=/tmp/matplotlib
# Healthy while the heartbeat task keeps reaching Telegram (it writes every 60 s).
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os,sys,time; sys.exit(time.time() - os.path.getmtime('/tmp/cash-interest.heartbeat') > 180)"]

CMD ["python", "-m", "cash_interest"]
