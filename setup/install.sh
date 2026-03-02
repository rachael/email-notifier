#!/usr/bin/env bash
# install.sh — deploy email-notifier to a DigitalOcean droplet (or any Ubuntu/Debian server).
#
# Run as root (or with sudo) directly on the server:
#   sudo bash setup/install.sh
#
# Prerequisites satisfied by this script:
#   - Python 3.11+
#   - Dedicated system user
#   - Virtualenv with all dependencies
#   - Systemd service + timer installed and enabled
#
# You still need to manually:
#   1. Copy credentials.json and token.json into /opt/email-notifier/
#   2. Create /opt/email-notifier/.env from the .env.example template
set -euo pipefail

APP_DIR="/opt/email-notifier"
APP_USER="email-notifier"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing system dependencies…"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Creating system user '${APP_USER}'…"
if ! id "${APP_USER}" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "==> Creating application directory at ${APP_DIR}…"
mkdir -p "${APP_DIR}"

echo "==> Copying application files…"
cp "${REPO_DIR}"/*.py       "${APP_DIR}/"
cp "${REPO_DIR}/requirements.txt" "${APP_DIR}/"

if [[ ! -f "${APP_DIR}/.env" ]]; then
    cp "${REPO_DIR}/.env.example" "${APP_DIR}/.env"
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
cp "${REPO_DIR}/setup/email-notifier.service" /etc/systemd/system/
cp "${REPO_DIR}/setup/email-notifier.timer"   /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now email-notifier.timer

echo ""
echo "==> Done! Next steps:"
echo ""
echo "  1. If you haven't yet, copy your credentials and token to the server:"
echo "       scp credentials.json token.json root@YOUR_DROPLET_IP:${APP_DIR}/"
echo "       sudo chown ${APP_USER}:${APP_USER} ${APP_DIR}/credentials.json ${APP_DIR}/token.json"
echo "       sudo chmod 640 ${APP_DIR}/credentials.json ${APP_DIR}/token.json"
echo ""
echo "  2. Fill in the remaining values in ${APP_DIR}/.env"
echo ""
echo "  3. Run a manual test:"
echo "       sudo systemctl start email-notifier.service"
echo "       sudo journalctl -u email-notifier -f"
echo ""
echo "  4. Check the timer schedule:"
echo "       sudo systemctl list-timers email-notifier.timer"
