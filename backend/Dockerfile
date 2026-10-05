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

FROM python:3.14-slim-bookworm@sha256:c8137f4c460908c8763f281c8f22c431eb5c538514ba9553fc3a89c06b7cfb88 AS runtime
LABEL org.opencontainers.image.title="hoje-api" \
      org.opencontainers.image.description="Hoje self-hosted personal planner: API and worker" \
      org.opencontainers.image.vendor="Hoje"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:/usr/lib/postgresql/17/bin:$PATH"
# The base image is pinned by digest, which also freezes its OS packages: apply the pending
# security updates at build time (the scan fails on fixed HIGH/CRITICAL CVEs).
# The worker runs the nightly backup with pg_dump, which must be at least as new as the server
# (PostgreSQL 17); bookworm ships only 15, so the client comes from the official PGDG apt
# repository. Its signing key is fetched over TLS and checked against the published fingerprint
# before it is trusted; the helper packages used for that are purged again.
ARG PGDG_KEY_FPR=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get install -y --no-install-recommends curl gnupg \
 && install -d -m 0755 /usr/share/keyrings \
 && curl -fsSL --retry 3 -o /tmp/pgdg.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && test "$(gpg --show-keys --with-colons /tmp/pgdg.asc | awk -F: '/^fpr:/ {print $10; exit}')" = "$PGDG_KEY_FPR" \
 && gpg --dearmor -o /usr/share/keyrings/postgresql-archive-keyring.gpg /tmp/pgdg.asc \
 && echo "deb [signed-by=/usr/share/keyrings/postgresql-archive-keyring.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && apt-get purge -y --auto-remove curl gnupg \
 && rm -rf /var/lib/apt/lists/* /tmp/pgdg.asc /root/.gnupg
# The app runs from its own venv; pip (and its vendored msgpack/setuptools, flagged by
# scanners) is not needed at runtime.
RUN python -m pip uninstall -y -q pip \
 && rm -rf /usr/local/lib/python3.13/ensurepip \
 && groupadd --system --gid 10001 hoje \
 && useradd --system --uid 10001 --gid hoje --home-dir /nonexistent --shell /usr/sbin/nologin hoje \
 && install -d -o 10001 -g 10001 -m 0700 /backups
WORKDIR /app
COPY --from=builder --chown=root:root /app /app
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"]
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
