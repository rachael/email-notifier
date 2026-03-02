#!/usr/bin/env python3
"""Gmail digest notifier — entry point.

Fetches emails since the last run, summarizes them via Claude, and pushes two
Pushover notifications: one for actionable items (high priority) and one FYI
digest (normal priority).

State is stored in .last_run as a UTC Unix timestamp so the script always
covers exactly the window since it last ran successfully, regardless of how
often the cron/timer fires.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from delivery import PushoverDelivery
from gmail_client import GmailClient
from summarizer import Summarizer

# ── Config ────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent
_STATE_FILE = _ROOT / ".last_run"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ── State helpers ─────────────────────────────────────────────────────────────


def _read_last_run(lookback_hours: int) -> datetime:
    if _STATE_FILE.exists():
        ts = float(_STATE_FILE.read_text().strip())
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    default = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    log.info("No prior state found; defaulting to %d-hour lookback.", lookback_hours)
    return default


def _write_last_run(dt: datetime) -> None:
    _STATE_FILE.write_text(str(dt.timestamp()))


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    load_dotenv()

    def require(key: str) -> str:
        val = os.environ.get(key, "").strip()
        if not val:
            log.error("Missing required environment variable: %s", key)
            sys.exit(1)
        return val

    gmail_credentials = require("GMAIL_CREDENTIALS_PATH")
    gmail_token = require("GMAIL_TOKEN_PATH")
    anthropic_key = require("ANTHROPIC_API_KEY")
    pushover_token = require("PUSHOVER_APP_TOKEN")
    pushover_user = require("PUSHOVER_USER_KEY")
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    lookback_hours = int(os.environ.get("DEFAULT_LOOKBACK_HOURS", "24"))

    now = datetime.now(tz=timezone.utc)
    since = _read_last_run(lookback_hours)
    log.info("Covering window: %s → %s", since.isoformat(), now.isoformat())

    # ── Fetch ──────────────────────────────────────────────────────────────
    gmail = GmailClient(gmail_credentials, gmail_token)
    gmail.authenticate()
    emails = gmail.fetch_messages_since(since)
    log.info("Fetched %d email(s).", len(emails))

    # ── Summarize ──────────────────────────────────────────────────────────
    summarizer = Summarizer(api_key=anthropic_key, model=model)
    action_summary, fyi_summary = summarizer.summarize(emails)

    # ── Deliver ────────────────────────────────────────────────────────────
    delivery = PushoverDelivery(pushover_token, pushover_user)

    period = f"{since.strftime('%-I%p').lower()}–{now.strftime('%-I%p').lower()}"

    if action_summary.lower() != "no action required.":
        delivery.send(
            title=f"Action needed ({period})",
            message=action_summary,
            priority=1,  # bypasses quiet hours
        )
    else:
        log.info("No actionable emails — skipping action notification.")

    delivery.send(
        title=f"Email digest ({period})",
        message=fyi_summary,
        priority=0,
    )

    # ── Persist state ──────────────────────────────────────────────────────
    _write_last_run(now)
    log.info("Done.")


if __name__ == "__main__":
    main()
