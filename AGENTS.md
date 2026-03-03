# AGENTS.md

Project knowledge base for AI agents collaborating on `email-notifier`.
This file is intentionally written for agents that may have no prior context —
explain the *why*, not just the *what*.  It will eventually be merged with a
broader cross-project knowledge base, so keep observations general where
possible.

---

## What this project does

Fetches Gmail via the Gmail API, summarizes new emails with Claude, and pushes
two daily Pushover notifications to the user's phone:

1. **Action digest** — emails requiring a reply, decision, payment, etc.
2. **FYI digest** — receipts, shipping updates, newsletters, account alerts.

The user's inbox is never touched.  The script is read-only at every layer.

---

## Architecture

```
Gmail API (read-only OAuth2)
        │
        ▼
  notifier.py        ← orchestrator, owns state (.last_run)
  ├── gmail_client.py   ← fetch messages for the current window
  ├── summarizer.py     ← two separate Claude calls (action / fyi)
  └── delivery.py       ← Pushover push notification
```

Each module has one responsibility and a narrow interface.  They can be tested,
replaced, or extended independently.

---

## Branching strategy

```
main ──────────── protected; what is running in production
  └── dev ───────── integration; CI runs here and on all PRs to main/dev
        └── claude/feature-name-<id>   ← feature branches (AI-authored)
        └── yourname/feature-name      ← feature branches (human-authored)
```

**Rules (enforce these even when working autonomously):**

- Never commit directly to `main` or `dev`.
- Feature branches target `dev` via PR.  `dev` targets `main` via PR.
- CI must be green before any merge.
- CD fires automatically on every push to `main` — merging to `main` is a
  deploy.  Do not merge to `main` if the server is in a broken state.
- AI agent branch names must start with `claude/` and end with the session ID
  supplied in task instructions.  This is enforced by the remote's receive
  hook; pushes to other names return 403.

---

## Development workflow

```bash
git checkout dev && git pull origin dev
git checkout -b claude/my-feature-abc123
# ... make atomic commits ...
git push -u origin claude/my-feature-abc123
# open PR → dev
```

Commit message conventions:
- `feat:` new functionality
- `fix:` bug fix
- `ci:` / `cd:` pipeline changes
- `docs:` documentation only
- `refactor:` no behaviour change
- `scaffold:` / `chore:` housekeeping

---

## Key files

| File | Role | Change with care? |
|---|---|---|
| `notifier.py` | Entry point; orchestration; state | Yes — touches everything |
| `gmail_client.py` | Gmail API + token refresh | Yes — token logic is subtle |
| `summarizer.py` | Claude prompts + API calls | Yes — prompt changes affect quality |
| `delivery.py` | Pushover API wrapper | Note the 1024-char message limit |
| `auth_setup.py` | One-time OAuth helper | Run locally only, never on server |
| `.last_run` | State file (gitignored) | Never commit; never delete on server |
| `setup/install.sh` | First-time server setup | Clones repo; runs once |
| `setup/update.sh` | Incremental deploy | Called by CD on every push to main |
| `setup/email-notifier.timer` | Schedule | Edit on server, then daemon-reload |
| `.github/workflows/ci.yml` | CI on PRs | Keep all checks fast (<60s) |
| `.github/workflows/deploy.yml` | CD on main push | Requires 3 GitHub secrets |

---

## Credentials and secrets

### What lives where

| Secret | Location | Committed? |
|---|---|---|
| `credentials.json` | Server `/opt/email-notifier/` | No — gitignored |
| `token.json` | Server `/opt/email-notifier/` | No — gitignored |
| `.env` | Server `/opt/email-notifier/` | No — gitignored |
| `DO_SSH_HOST/USER/PRIVATE_KEY` | GitHub repo secrets | No |

### The OAuth token lifecycle

1. `auth_setup.py` runs **locally** (needs a browser) → writes `token.json`.
2. `token.json` is `scp`'d to the server.
3. On every subsequent run, `GmailClient.authenticate()` auto-refreshes the
   access token from the stored refresh token.  No human action needed.
4. If the token is ever revoked (e.g. password change, Google security alert,
   scope change), step 1–2 must be repeated.

**Critical:** `auth_setup.py` will hang or fail on a headless server because
it tries to open a browser.  Always run it locally.

### Gmail OAuth scope

The scope is `gmail.readonly`.  This is intentional and must not be widened
without explicit discussion.  A read-only token cannot send, delete, or modify
anything.  If a future feature requires writes (e.g. auto-labelling), treat
that as a security decision, not just an implementation detail.

---

## Environment variables

All loaded from `.env` via `python-dotenv`.  Missing required variables cause
an immediate `sys.exit(1)` with a clear message.  See `.env.example` for
full descriptions.

| Variable | Required | Default |
|---|---|---|
| `GMAIL_CREDENTIALS_PATH` | Yes | — |
| `GMAIL_TOKEN_PATH` | Yes | — |
| `ANTHROPIC_API_KEY` | Yes | — |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-6` |
| `PUSHOVER_APP_TOKEN` | Yes | — |
| `PUSHOVER_USER_KEY` | Yes | — |
| `DEFAULT_LOOKBACK_HOURS` | No | `24` |

---

## CI/CD

### CI (`.github/workflows/ci.yml`)

Runs on every PR to `dev` or `main`, and on direct pushes to `dev`:
- `ruff check .` — linting
- `python -m compileall` — syntax check
- Shell script asserting all env vars are documented in `.env.example`

Keep CI under 60 seconds.  If you add a slow check, make it a separate job.

### CD (`.github/workflows/deploy.yml`)

Runs on every push to `main`.  SSHes into the DO droplet and runs
`setup/update.sh`, which does `git pull origin main` + `pip install`.

**GitHub secrets required:**

| Secret | Value |
|---|---|
| `DO_SSH_HOST` | Droplet IP or hostname |
| `DO_SSH_USER` | User with write access to `/opt/email-notifier` |
| `DO_SSH_PRIVATE_KEY` | Private key (public key must be in server's `authorized_keys`) |

No service restart is needed after a deploy.  The notifier is a `oneshot`
systemd service driven by a timer — the next timer fire automatically uses
the new code.

---

## Gotchas

### Gmail `after:` filter is date-granular, not timestamp-granular

`after:YYYY/MM/DD` matches by calendar day.  If the script runs at 11:59 PM
and again at midnight, the second run re-fetches the emails from earlier that
evening.  The `.last_run` state file handles this at the app level by recording
the exact timestamp of the previous run.  Claude may occasionally summarize
edge-case emails twice, which is acceptable for a personal digest.

### Pushover message limit is 1024 characters

`delivery.py` silently truncates to 1024 chars.  If summaries are consistently
getting cut off, either reduce `max_tokens` in `summarizer.py` or split the
notification into multiple messages.

### The action notification is conditionally suppressed

`notifier.py` skips the action push if `action_summary` matches
`"no action required."` (case-insensitive).  If Claude returns a different
phrasing for an empty result, the check fails silently and sends a useless
notification.  If you change the prompt's empty-state instruction, update the
check in `notifier.py:main()` to match.

### systemd timer `Persistent=true` is the self-healing mechanism

Without `Persistent=true`, a server reboot during a scheduled window means
that run is silently skipped.  With it, the timer fires immediately on the next
startup.  Do not remove this setting.  Do not add a cron fallback — it would
cause double runs.

### The `.last_run` state file must survive deploys

`setup/update.sh` does `git pull` — it does not touch `.last_run`.  If you
ever wipe and reinstall the server, `.last_run` is lost.  The first run will
fall back to `DEFAULT_LOOKBACK_HOURS`, producing a larger-than-usual digest.
This is safe; just warn the user if you do a full reinstall.

---

## Model selection

Default: `claude-sonnet-4-6` (good balance of quality and cost for a personal
digest running twice a day).

- If summaries feel too terse or miss context: try `claude-opus-4-6`.
- If cost is a concern: `claude-haiku-4-5-20251001` works but needs more
  prompt engineering to maintain separation between action and FYI items.

Change via `CLAUDE_MODEL` in `.env` — no code changes needed.

---

## Extending the project

### Adding a delivery channel

`delivery.py` is the only place to change.  Create a class with a
`send(title, message, priority)` method, instantiate it in
`notifier.py:main()`.  Add any new env vars to `.env.example` and update the
CI env-completeness check in `ci.yml`.

### Adding a new email source (not Gmail)

Implement the same interface as `GmailClient`: an `authenticate()` method and
a `fetch_messages_since(since: datetime) -> list[dict]` method returning the
same dict schema (`subject`, `from`, `date`, `body`, `snippet`, `labels`).
Swap it in `notifier.py`.

### Changing the summarization logic

Edit the prompts in `summarizer.py`.  Key constraints to preserve:
- The action prompt must produce a parseable empty-state string (currently
  `"No action required."`) that matches the check in `notifier.py`.
- Both prompts receive the full email list — do not split emails between calls.

---

## Lessons learned (share with other agents)

**1. Windowed state tracking beats fixed time windows.**
Storing the last-run timestamp in `.last_run` means the script always covers
the exact gap since the previous run — no doubles, no gaps — regardless of
schedule drift, missed runs, or manual re-runs.  A naïve `last 24 hours` query
creates gaps whenever a run is slightly delayed.

**2. Two separate Claude calls produce better results than one.**
Asking Claude to do "action items AND a summary" in a single response produces
worse separation.  Two focused calls with explicit success criteria
(`"if nothing, say exactly: No action required."`) give more reliable,
parseable output.  The extra API call costs pennies and is worth it.

**3. Read-only OAuth scope is a forcing function for correctness.**
Restricting to `gmail.readonly` prevents a whole class of bugs (accidentally
marking emails read, auto-archiving, etc.) and limits the blast radius of a
leaked token.  Treat any request to widen the scope as a security decision.

**4. Never route the source of truth through the notifier.**
The user's friend filtered all email into a secondary inbox and sent summaries.
Any downtime = lost mail.  Our approach is read-only: Gmail is always the
source of truth; the notifier is just a lens.

**5. `git clone` on the server enables clean CD.**
The initial `cp`-based install broke CD (no way to `git pull`).  Cloning the
repo on first install makes `update.sh` trivial and keeps deploys atomic and
reproducible.  If you're setting up a scheduled script on a server, clone from
the start.

**6. `Persistent=true` in systemd timers is non-obvious but critical.**
Without it, a rebooted server silently skips all missed runs — the timer treats
the missed windows as gone.  With it, the timer fires immediately on startup
for any missed window.  Always include this in timer units for non-interactive
scheduled tasks.

**7. Install scripts should be idempotent.**
Both `install.sh` and `update.sh` are safe to re-run.  `git pull` is a no-op
if already current; `pip install` is a no-op if requirements haven't changed;
`useradd` is guarded by an `id` check.  Idempotent scripts make debugging and
disaster recovery dramatically easier.

**8. Atomic commits make history useful.**
Each commit in this project corresponds to one logical unit (one module, one
workflow, one concern).  This makes `git bisect`, `git log`, and code review
tractable.  Resist the urge to batch unrelated changes.
