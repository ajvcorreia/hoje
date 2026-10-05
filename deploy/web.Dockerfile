# syntax=docker/dockerfile:1
# Hoje web image: built SPA + Caddy. Build context: repository root.

FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend/ ./
RUN npm run build

# Caddy compiled with the current Go toolchain and patched dependencies: the upstream
# release binary lags behind Go and x/* security fixes, which fails the image scan.
FROM golang:1.27-alpine@sha256:8a5910f31396cd4d89662f56c68b3ae31d374308270a1c3bd96672ee5ed43414 AS caddy
ARG CADDY_VERSION=v2.11.4
WORKDIR /src
RUN printf '%s\n' 'package main' \
      'import (' \
      '	caddycmd "github.com/caddyserver/caddy/v2/cmd"' \
      '	_ "github.com/caddyserver/caddy/v2/modules/standard"' \
      ')' \
      'func main() { caddycmd.Main() }' > main.go \
 && go mod init hoje/caddy
RUN --mount=type=cache,target=/go/pkg/mod \
    go get github.com/caddyserver/caddy/v2@${CADDY_VERSION} \
        golang.org/x/crypto@v0.55.0 \
        google.golang.org/grpc@v1.83.2 \
 && go mod tidy \
 && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /usr/bin/caddy .

FROM caddy:2-alpine@sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9 AS runtime
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
LABEL org.opencontainers.image.title="hoje-web" \
      org.opencontainers.image.description="Hoje self-hosted personal planner: web (Caddy + SPA)" \
      org.opencontainers.image.vendor="Hoje"
# The base image is pinned by digest, which also freezes its OS packages: apply the pending
# security updates at build time (the scan fails on fixed HIGH/CRITICAL CVEs).
# Non-root Caddy that can still bind 80/443 via file capability.
RUN apk upgrade --no-cache \
 && apk add --no-cache libcap \
 && addgroup -S -g 10001 hoje \
 && adduser -S -u 10001 -G hoje -H -h /data -s /sbin/nologin hoje \
 && setcap cap_net_bind_service=+ep /usr/bin/caddy \
 && apk del libcap \
 && mkdir -p /data /config \
 && chown -R hoje:hoje /data /config
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /frontend/dist /srv
ENV XDG_DATA_HOME=/data \
    XDG_CONFIG_HOME=/config \
    SITE_ADDRESS=:8080
USER 10001:10001
EXPOSE 80 443 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:2020/caddy-health"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
