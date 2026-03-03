#!/usr/bin/env bash
# install.sh — first-time deployment to a DigitalOcean droplet (or any Ubuntu/Debian server).
#
# Run as root on the server:
#   sudo bash setup/install.sh
#
# What this script does:
#   - Installs Python and git
#   - Creates a dedicated system user
#   - Clones the repo to /opt/email-notifier (enabling git pull for future updates)
#   - Creates a virtualenv and installs dependencies
#   - Installs and enables the systemd service + timer
#
# What you still need to do after running this:
#   1. Copy credentials.json and token.json into /opt/email-notifier/
#   2. Fill in /opt/email-notifier/.env

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
# Set this to your repo's HTTPS clone URL before running.
# For private repos, use an SSH URL and ensure root has access via a deploy key.
REPO_URL="${REPO_URL:-https://github.com/yourname/email-notifier.git}"

APP_DIR="/opt/email-notifier"
APP_USER="email-notifier"
# ──────────────────────────────────────────────────────────────────────────────

echo "==> Installing system dependencies…"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git

echo "==> Creating system user '${APP_USER}'…"
if ! id "${APP_USER}" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "==> Cloning repository to ${APP_DIR}…"
if [[ -d "${APP_DIR}/.git" ]]; then
    echo "    (already cloned — pulling latest main instead)"
    git -C "${APP_DIR}" pull origin main
else
    git clone "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Bootstrapping .env…"
if [[ ! -f "${APP_DIR}/.env" ]]; then
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    echo ""
    echo "  !! .env created from template. Edit it before starting the timer:"
    echo "       nano ${APP_DIR}/.env"
    echo ""
fi

echo "==> Creating Python virtualenv…"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

echo "==> Setting ownership…"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
# .env contains secrets — readable only by the app user.
chmod 640 "${APP_DIR}/.env"

echo "==> Installing systemd units…"
cp "${APP_DIR}/setup/email-notifier.service" /etc/systemd/system/
cp "${APP_DIR}/setup/email-notifier.timer"   /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now email-notifier.timer

echo ""
echo "==> Done! Next steps:"
echo ""
echo "  1. Copy your credentials and token to the server:"
echo "       scp credentials.json token.json root@YOUR_DROPLET_IP:${APP_DIR}/"
echo "       chown ${APP_USER}:${APP_USER} ${APP_DIR}/credentials.json ${APP_DIR}/token.json"
echo "       chmod 640 ${APP_DIR}/credentials.json ${APP_DIR}/token.json"
echo ""
echo "  2. Fill in the remaining values in ${APP_DIR}/.env"
echo ""
echo "  3. Run a manual test:"
echo "       sudo systemctl start email-notifier.service"
echo "       sudo journalctl -u email-notifier -f"
echo ""
echo "  4. Check the timer schedule:"
echo "       sudo systemctl list-timers email-notifier.timer"
