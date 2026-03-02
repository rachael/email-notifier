"""Pushover notification delivery.

Pushover docs: https://pushover.net/api
Priority levels:
  -1  quiet    — no sound/vibration, still visible
   0  normal   — default sound
   1  high     — bypasses quiet hours
"""

import logging

import requests

log = logging.getLogger(__name__)

_API_URL = "https://api.pushover.net/1/messages.json"
# Pushover caps message body at 1024 characters.
_MAX_MESSAGE_CHARS = 1024


class PushoverDelivery:
    def __init__(self, app_token: str, user_key: str) -> None:
        self._app_token = app_token
        self._user_key = user_key

    def send(self, title: str, message: str, priority: int = 0) -> None:
        """Send a push notification.  Raises on HTTP or Pushover API error."""
        if len(message) > _MAX_MESSAGE_CHARS:
            message = message[: _MAX_MESSAGE_CHARS - 3] + "..."

        response = requests.post(
            _API_URL,
            data={
                "token": self._app_token,
                "user": self._user_key,
                "title": title,
                "message": message,
                "priority": priority,
            },
            timeout=15,
        )
        response.raise_for_status()

        body = response.json()
        if body.get("status") != 1:
            raise RuntimeError(f"Pushover rejected message: {body.get('errors')}")

        log.info("Pushover notification sent: %r", title)
