# syntax=docker/dockerfile:1
# Hoje API + worker image (context: backend/). Same image, different command.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first (cache-friendly), then the project itself.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project
COPY pyproject.toml uv.lock alembic.ini ./
COPY hoje ./hoje
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm@sha256:5024f48ba9441d4b13a95d3945abc6365538e3a31109833367a1923523c6efed AS runtime
LABEL org.opencontainers.image.title="hoje-api" \
      org.opencontainers.image.description="Hoje self-hosted personal planner: API and worker" \
      org.opencontainers.image.vendor="Hoje"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
# The base image is pinned by digest, which also freezes its OS packages: apply the pending
# security updates at build time (the scan fails on fixed HIGH/CRITICAL CVEs).
RUN apt-get update \
 && apt-get -y upgrade \
 && rm -rf /var/lib/apt/lists/*
# The app runs from its own venv; pip (and its vendored msgpack/setuptools, flagged by
# scanners) is not needed at runtime.
RUN python -m pip uninstall -y -q pip \
 && rm -rf /usr/local/lib/python3.13/ensurepip \
 && groupadd --system --gid 10001 hoje \
 && useradd --system --uid 10001 --gid hoje --home-dir /nonexistent --shell /usr/sbin/nologin hoje
WORKDIR /app
COPY --from=builder --chown=root:root /app /app
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"]
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
