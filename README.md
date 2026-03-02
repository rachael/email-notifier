# email-notifier

Fetches your Gmail every time it runs, asks Claude to write two summaries, and
pushes them to your phone via Pushover:

- **Action needed** (high-priority, bypasses quiet hours) — emails you must
  respond to, decide on, pay, schedule, etc.
- **Email digest** (normal priority) — receipts, shipping updates, news, and
  anything else worth knowing but not acting on.

The script tracks its own run timestamp so each notification covers exactly the
window since the last successful run — no double-counting, no gaps.

---

## How it works

```
Gmail API (read-only)
       │
       ▼
  notifier.py  ──► Claude (summarize) ──► Pushover ──► your phone
       │
  .last_run  (persists the window boundary between runs)
```

Credentials never touch your inbox routing — your Gmail works exactly as it
always has.

---

## Prerequisites

| What | Where to get it |
|---|---|
| Google Cloud project with Gmail API enabled | [console.cloud.google.com](https://console.cloud.google.com) |
| OAuth 2.0 Client ID (Desktop app type) | APIs & Services → Credentials |
| Anthropic API key | [console.anthropic.com](https://console.anthropic.com) |
| Pushover account + app token | [pushover.net](https://pushover.net) — $5 one-time app purchase |

---

## Local setup (do this first, on your own machine)

### 1. Clone and install

```bash
git clone https://github.com/yourname/email-notifier.git
cd email-notifier
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Download OAuth credentials from Google Cloud

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and
   create a project (or use an existing one).
2. Enable the **Gmail API**: APIs & Services → Enable APIs → search "Gmail API".
3. Create credentials: APIs & Services → Credentials → Create Credentials →
   **OAuth client ID** → Application type: **Desktop app**.
4. Download the JSON file and save it as `credentials.json` in the repo root.

### 3. Run the one-time auth flow

```bash
python auth_setup.py --credentials credentials.json --token token.json
```

This opens a browser, shows Google's consent screen, and writes `token.json`.
The notifier refreshes this token automatically from now on — you won't need
to repeat this step.

### 4. Test it locally

```bash
cp .env.example .env
# Fill in all values in .env
python notifier.py
```

Check for two Pushover notifications on your phone.

---

## Server deployment (DigitalOcean or any Ubuntu/Debian VPS)

The notifier runs as a **systemd timer** — the OS-native scheduler.  This
gives you:

- Runs at 8 AM and 5 PM daily (configurable).
- **`Persistent=true`**: if the server was off during a scheduled run (reboot,
  brief outage), the timer fires immediately on the next startup and catches
  up — no missed digests.
- Logs via `journald` with structured output and automatic rotation.
- Runs as a dedicated non-root user for isolation.

### 1. Copy files to your server

```bash
# From your local machine, in the repo root:
scp -r . root@YOUR_DROPLET_IP:/tmp/email-notifier-src/
```

### 2. SSH in and run the installer

```bash
ssh root@YOUR_DROPLET_IP
cd /tmp/email-notifier-src
sudo bash setup/install.sh
```

The installer:
- Installs Python if needed
- Creates a dedicated `email-notifier` system user
- Copies code to `/opt/email-notifier/`
- Creates a virtualenv and installs dependencies
- Installs and **enables** the systemd service and timer
- Creates `/opt/email-notifier/.env` from the template for you to fill in

### 3. Copy your secrets to the server

```bash
# From your local machine:
scp credentials.json token.json root@YOUR_DROPLET_IP:/opt/email-notifier/
ssh root@YOUR_DROPLET_IP \
  "chown email-notifier:email-notifier /opt/email-notifier/credentials.json /opt/email-notifier/token.json && \
   chmod 640 /opt/email-notifier/credentials.json /opt/email-notifier/token.json"
```

### 4. Fill in the .env on the server

```bash
ssh root@YOUR_DROPLET_IP
nano /opt/email-notifier/.env
```

Fill in all values (see `.env.example` for descriptions).  The paths are
already set to `/opt/email-notifier/...` by default.

### 5. Test it manually

```bash
sudo systemctl start email-notifier.service
sudo journalctl -u email-notifier -f
```

You should see the run log and receive two Pushover notifications.

### 6. Confirm the timer is scheduled

```bash
sudo systemctl list-timers email-notifier.timer
```

Output looks like:

```
NEXT                        LEFT      LAST                        PASSED    UNIT
Mon 2026-03-03 08:00:00 UTC 14h left  Mon 2026-03-02 17:00:12 UTC 1min ago  email-notifier.timer
```

That's it.  The timer runs automatically on every boot and at each scheduled
time, indefinitely.

---

## Customising the schedule

Edit `/etc/systemd/system/email-notifier.timer` on the server:

```ini
[Timer]
OnCalendar=*-*-* 07:30:00   # morning digest
OnCalendar=*-*-* 16:00:00   # afternoon digest
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart email-notifier.timer
```

`OnCalendar` uses the system timezone.  To change the server timezone:
```bash
sudo timedatectl set-timezone America/New_York
```

---

## Operations

| Task | Command |
|---|---|
| View recent logs | `journalctl -u email-notifier -n 50` |
| Follow logs live | `journalctl -u email-notifier -f` |
| Run manually now | `sudo systemctl start email-notifier.service` |
| Check timer schedule | `systemctl list-timers email-notifier.timer` |
| Disable the timer | `sudo systemctl disable --now email-notifier.timer` |
| Update code | `scp *.py root@DROPLET:/opt/email-notifier/` |

---

## Repository layout

```
email-notifier/
├── notifier.py          # entry point — orchestrates fetch → summarize → deliver
├── gmail_client.py      # Gmail API wrapper (read-only OAuth2)
├── summarizer.py        # Claude prompts for action and FYI summaries
├── delivery.py          # Pushover API wrapper
├── auth_setup.py        # one-time OAuth helper (run locally, not on server)
├── requirements.txt
├── .env.example         # config template with documentation
└── setup/
    ├── email-notifier.service   # systemd service unit
    ├── email-notifier.timer     # systemd timer unit (schedule lives here)
    └── install.sh               # one-command server installer
```

---

## Security notes

- The Gmail OAuth scope is **read-only** (`gmail.readonly`). A leaked token
  cannot send, delete, or modify anything.
- `token.json` and `credentials.json` are in `.gitignore` — they are never
  committed.
- On the server, both files are owned by the `email-notifier` user and
  chmod `640` (not readable by other users).
- The `.env` file is also `640` — secrets never appear in `ps` output or
  systemd unit files.
