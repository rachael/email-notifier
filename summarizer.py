"""Claude-powered email summarizer.

Produces two independent summaries from a batch of email dicts:
  - action_summary: things the user must do something about
  - fyi_summary:    things worth knowing that need no action
"""

import logging

import anthropic

log = logging.getLogger(__name__)

# Maximum characters of formatted email text sent to Claude.
# ~120 k chars ≈ ~30 k tokens — well within claude-sonnet-4-6's context window.
MAX_EMAIL_CHARS = 120_000

_ACTION_PROMPT = """\
You are an assistant reviewing emails for your user.

Your job: identify ONLY emails that require the user to take action — reply, \
make a decision, schedule something, pay a bill, sign a document, etc.

For each actionable email output a single bullet in this exact format:
• [Sender name] — [Subject] → [one sentence describing the required action]

Rules:
- Skip newsletters, marketing, automated alerts, receipts, shipping \
notifications, and anything purely informational.
- If nothing requires action, respond with exactly: No action required.
- Do not add any preamble or closing remarks.

EMAILS:
{emails}"""

_FYI_PROMPT = """\
You are an assistant reviewing emails for your user.

Your job: summarize anything the user would want to be aware of but does NOT \
need to act on — shipping updates, receipts, account alerts, news digests, \
calendar invites they've already accepted, etc.

Group related items under a short bold heading (e.g. **Orders & Shipping**). \
Be concise — one line per item where possible.

Rules:
- Skip pure spam and trivial automated notifications with no useful content.
- If nothing is worth noting, respond with exactly: Nothing notable.
- Do not add any preamble or closing remarks.

EMAILS:
{emails}"""


class Summarizer:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def summarize(self, emails: list[dict]) -> tuple[str, str]:
        """Return (action_summary, fyi_summary) for the given email list."""
        if not emails:
            return "No emails in the period.", "No emails in the period."

        email_text = _format_emails(emails)
        if len(email_text) > MAX_EMAIL_CHARS:
            log.warning(
                "Email text truncated from %d to %d chars for LLM call.",
                len(email_text),
                MAX_EMAIL_CHARS,
            )
            email_text = email_text[:MAX_EMAIL_CHARS]

        action = self._call(_ACTION_PROMPT.format(emails=email_text))
        fyi = self._call(_FYI_PROMPT.format(emails=email_text))

        log.info("Summarization complete. Action: %d chars, FYI: %d chars.", len(action), len(fyi))
        return action, fyi

    def _call(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


def _format_emails(emails: list[dict]) -> str:
    parts = []
    for i, msg in enumerate(emails, 1):
        parts.append(
            f"--- [{i}] ---\n"
            f"From: {msg['from']}\n"
            f"Date: {msg['date']}\n"
            f"Subject: {msg['subject']}\n"
            f"Body:\n{msg['body']}\n"
        )
    return "\n".join(parts)
