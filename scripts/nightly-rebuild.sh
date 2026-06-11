#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "Docker Compose is required but was not found."
    exit 1
fi

export GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

APP_SERVICES=(backend worker celery-beat frontend)
RUNTIME_SERVICES=(backend worker celery-beat frontend nginx)
LETSENCRYPT_DIR="/etc/letsencrypt/live/phonereport.wi-fiber.io"
TLS_DIR="$ROOT_DIR/docker/ssl"

restore_tls_certs() {
    if [ -f "$LETSENCRYPT_DIR/fullchain.pem" ] && [ -f "$LETSENCRYPT_DIR/privkey.pem" ]; then
        echo "Refreshing TLS certs from Let's Encrypt"
        cp "$LETSENCRYPT_DIR/fullchain.pem" "$TLS_DIR/cert.pem"
        cp "$LETSENCRYPT_DIR/privkey.pem" "$TLS_DIR/key.pem"
    else
        echo "Let's Encrypt certs not found at $LETSENCRYPT_DIR; leaving existing TLS files in place"
    fi
}

echo "Building nightly images for commit $GIT_COMMIT at $BUILD_TIMESTAMP"
"${COMPOSE_CMD[@]}" build --no-cache "${APP_SERVICES[@]}"

restore_tls_certs

echo "Recreating application services after successful build"
"${COMPOSE_CMD[@]}" up -d --force-recreate --remove-orphans "${RUNTIME_SERVICES[@]}"

echo "Nightly rebuild completed."