#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v git >/dev/null 2>&1; then
    echo "git is required but was not found in PATH."
    exit 1
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "Docker Compose is required but was not found."
    exit 1
fi

BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"

if [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ]; then
    echo "Could not determine the current branch. Pass it explicitly, for example: ./scripts/update-production.sh main"
    exit 1
fi

echo "Updating branch: $BRANCH"
git fetch --prune origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

export GIT_COMMIT="$(git rev-parse --short HEAD)"
export BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "Building release for commit $GIT_COMMIT at $BUILD_TIMESTAMP"
"${COMPOSE_CMD[@]}" up -d --build --remove-orphans backend worker celery-beat frontend nginx

echo "Deployment complete. Quality & Health should now show commit $GIT_COMMIT."
