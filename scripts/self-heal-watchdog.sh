#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOCK_FILE="/var/lock/phonereports-watchdog.lock"
STATE_DIR="/var/lib/phonereports-watchdog"
STATE_FILE="$STATE_DIR/state.env"
LOG_TAG="phonereports-watchdog"

FAILURE_THRESHOLD_SECONDS="${FAILURE_THRESHOLD_SECONDS:-300}"
RECOVERY_COOLDOWN_SECONDS="${RECOVERY_COOLDOWN_SECONDS:-300}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 0
fi

mkdir -p "$STATE_DIR"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    logger -t "$LOG_TAG" "Docker Compose is not available."
    exit 1
fi

read_env_var() {
    local key="$1"
    local default_value="$2"

    if [ -f .env ]; then
        local line
        line="$(grep -E "^${key}=" .env | tail -n 1 || true)"
        if [ -n "$line" ]; then
            line="${line#*=}"
            line="${line%\"}"
            line="${line#\"}"
            line="${line%\'}"
            line="${line#\'}"
            printf '%s' "$line"
            return
        fi
    fi

    printf '%s' "$default_value"
}

DB_USER="$(read_env_var "DB_USER" "phonereports_user")"
DB_NAME="$(read_env_var "DB_NAME" "phonereports")"

FAIL_SINCE_EPOCH=0
LAST_RECOVERY_EPOCH=0

if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
fi

now_epoch="$(date +%s)"
failure_reasons=()

check_container_running() {
    local container_name="$1"
    local running
    running="$(docker inspect -f '{{.State.Running}}' "$container_name" 2>/dev/null || true)"
    [ "$running" = "true" ]
}

check_container_healthy() {
    local container_name="$1"
    local health
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_name" 2>/dev/null || true)"
    [ "$health" = "healthy" ] || [ "$health" = "none" ]
}

if ! check_container_running "fpbx-analytics-nginx"; then
    failure_reasons+=("nginx container is not running")
fi

if ! curl -kfsS --max-time 8 https://localhost >/dev/null 2>&1; then
    failure_reasons+=("nginx endpoint is not serving https://localhost")
fi

if ! check_container_running "fpbx-analytics-backend"; then
    failure_reasons+=("backend container is not running")
elif ! check_container_healthy "fpbx-analytics-backend"; then
    failure_reasons+=("backend container is not healthy")
fi

if ! check_container_running "fpbx-analytics-db"; then
    failure_reasons+=("database container is not running")
elif ! docker exec fpbx-analytics-db pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    failure_reasons+=("database is not accepting connections")
fi

if [ "${#failure_reasons[@]}" -eq 0 ]; then
    cat >"$STATE_FILE" <<EOF
FAIL_SINCE_EPOCH=0
LAST_RECOVERY_EPOCH=${LAST_RECOVERY_EPOCH:-0}
EOF
    exit 0
fi

if [ "${FAIL_SINCE_EPOCH:-0}" -eq 0 ]; then
    FAIL_SINCE_EPOCH="$now_epoch"
fi

failure_age="$((now_epoch - FAIL_SINCE_EPOCH))"

cat >"$STATE_FILE" <<EOF
FAIL_SINCE_EPOCH=$FAIL_SINCE_EPOCH
LAST_RECOVERY_EPOCH=${LAST_RECOVERY_EPOCH:-0}
EOF

logger -t "$LOG_TAG" "Detected failures: ${failure_reasons[*]}; failure_age=${failure_age}s"

if [ "$failure_age" -lt "$FAILURE_THRESHOLD_SECONDS" ]; then
    exit 1
fi

if [ "$((now_epoch - LAST_RECOVERY_EPOCH))" -lt "$RECOVERY_COOLDOWN_SECONDS" ]; then
    logger -t "$LOG_TAG" "Skipping recovery due to cooldown (${RECOVERY_COOLDOWN_SECONDS}s)."
    exit 1
fi

logger -t "$LOG_TAG" "Failure persisted for ${failure_age}s, starting recovery."

APP_SERVICES=(backend worker celery-beat frontend)
RUNTIME_SERVICES=(backend worker celery-beat frontend nginx)

"${COMPOSE_CMD[@]}" build "${APP_SERVICES[@]}"
"${COMPOSE_CMD[@]}" up -d --force-recreate --remove-orphans "${RUNTIME_SERVICES[@]}"
"${COMPOSE_CMD[@]}" restart nginx

LAST_RECOVERY_EPOCH="$now_epoch"

cat >"$STATE_FILE" <<EOF
FAIL_SINCE_EPOCH=0
LAST_RECOVERY_EPOCH=$LAST_RECOVERY_EPOCH
EOF

logger -t "$LOG_TAG" "Recovery completed successfully."