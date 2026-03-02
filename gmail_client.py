"""Gmail API client — read-only access, OAuth2 with persisted token refresh."""

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
# Max body chars fed to the LLM per message — keeps token costs predictable.
BODY_CHAR_LIMIT = 2500


class GmailClient:
    def __init__(self, credentials_path: str, token_path: str) -> None:
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._service = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Load or refresh credentials, prompting for auth if needed.

        On a headless server the token file must already exist (generated
        locally via auth_setup.py).  On a local machine with a browser this
        will open the OAuth consent screen automatically.
        """
        creds = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                log.info("Refreshing expired Gmail token.")
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"OAuth client secrets not found at {self.credentials_path}. "
                        "Download from Google Cloud Console → APIs & Services → Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_path.write_text(creds.to_json())
            log.info("Gmail token written to %s", self.token_path)

        self._service = build("gmail", "v1", credentials=creds)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_messages_since(self, since: datetime) -> list[dict]:
        """Return a flat list of message dicts for all mail since *since*."""
        assert self._service is not None, "Call authenticate() first."

        # Gmail's after: filter is date-granular (YYYY/MM/DD).
        after_str = since.strftime("%Y/%m/%d")
        query = f"after:{after_str}"
        log.info("Gmail query: %s", query)

        message_ids = self._list_message_ids(query)
        log.info("Found %d messages; fetching details.", len(message_ids))

        messages = []
        for msg_id in message_ids:
            msg = self._fetch_one(msg_id)
            if msg:
                messages.append(msg)

        return messages

    def _list_message_ids(self, query: str) -> list[str]:
        ids = []
        page_token = None

        while True:
            kwargs: dict = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                kwargs["pageToken"] = page_token

            result = self._service.users().messages().list(**kwargs).execute()
            ids.extend(m["id"] for m in result.get("messages", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return ids

    def _fetch_one(self, message_id: str) -> dict | None:
        try:
            raw = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as exc:
            log.warning("Could not fetch message %s: %s", message_id, exc)
            return None

        headers = {h["name"]: h["value"] for h in raw["payload"].get("headers", [])}
        body = _extract_text_body(raw["payload"])

        return {
            "id": message_id,
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": raw.get("snippet", ""),
            "body": (body or raw.get("snippet", ""))[:BODY_CHAR_LIMIT],
            "labels": raw.get("labelIds", []),
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_text_body(payload: dict) -> str:
    """Recursively pull the first text/plain part out of a MIME payload."""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_text_body(part)
        if text:
            return text

    return ""
