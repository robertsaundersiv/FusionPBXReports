#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ "${EUID}" -ne 0 ]; then
    echo "Run as root: sudo bash ./scripts/install-watchdog.sh"
    exit 1
fi

install -m 755 "$ROOT_DIR/scripts/self-heal-watchdog.sh" /opt/phonereports/scripts/self-heal-watchdog.sh
install -m 644 "$ROOT_DIR/ops/systemd/phonereports-watchdog.service" /etc/systemd/system/phonereports-watchdog.service
install -m 644 "$ROOT_DIR/ops/systemd/phonereports-watchdog.timer" /etc/systemd/system/phonereports-watchdog.timer

mkdir -p /var/lib/phonereports-watchdog
chown root:root /var/lib/phonereports-watchdog

systemctl daemon-reload
systemctl enable --now phonereports-watchdog.timer

echo "Watchdog installed and timer started."
systemctl status phonereports-watchdog.timer --no-pager --lines=5 || true
