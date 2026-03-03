#!/usr/bin/env bash
# update.sh — pull latest main and reinstall dependencies.
#
# Called automatically by the GitHub Actions CD workflow on every push to main.
# Safe to run manually at any time — git pull is a no-op if already current.
#
# Run as root (or a user with write access to /opt/email-notifier):
#   sudo bash /opt/email-notifier/setup/update.sh

set -euo pipefail

APP_DIR="/opt/email-notifier"

echo "==> Pulling latest code…"
git -C "${APP_DIR}" pull origin main

echo "==> Reinstalling dependencies (no-op if requirements.txt unchanged)…"
"${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

echo "==> Update complete at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
# No service restart needed: the notifier is a oneshot service driven by a
# timer.  The next timer fire automatically picks up the new code.
