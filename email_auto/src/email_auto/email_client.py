from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
import imaplib
import os
import re


@dataclass(frozen=True)
class EmailCredentials:
    server: str
    port: int
    account: str
    password: str


@dataclass(frozen=True)
class EmailMessageData:
    uid: str
    email_id: str
    sender: str
    sender_email: str
    subject: str
    date: str
    received_at: datetime
    body: str

    def to_prompt_payload(self) -> dict[str, str]:
        return {
            "email_id": self.email_id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "date": self.date,
            "body": self.body,
        }


def load_email_credentials() -> EmailCredentials:
    server = os.environ.get("IMAP_SERVER", "").strip()
    port = int(os.environ.get("IMAP_PORT", "993"))
    account = os.environ.get("EMAIL_ACCOUNT", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").replace(" ","")
    missing = [
        name
        for name, value in {
            "IMAP_SERVER": server,
            "EMAIL_ACCOUNT": account,
            "EMAIL_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    return EmailCredentials(server=server, port=port, account=account, password=password)


class IMAPEmailClient:
    def __init__(self, credentials: EmailCredentials):
        self.credentials = credentials

    def fetch_recent_emails(
        self,
        mailbox: str,
        unread_only: bool,
        lookback_hours: int,
        max_messages: int,
        allow_senders: list[str],
        exclude_senders: list[str],
    ) -> list[EmailMessageData]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        since_token = cutoff.strftime("%d-%b-%Y")
        criteria = f"(SINCE {since_token})"
        if unread_only:
            criteria = f"(UNSEEN SINCE {since_token})"

        connection = imaplib.IMAP4_SSL(self.credentials.server, self.credentials.port)
        try:
            connection.login(self.credentials.account, self.credentials.password)
            status, _ = connection.select(mailbox)
            if status != "OK":
                raise RuntimeError(f"Unable to select mailbox {mailbox}")

            status, data = connection.uid("search", None, criteria)
            if status != "OK":
                raise RuntimeError("Unable to search mailbox")

            uids = [value.decode("utf-8") for value in data[0].split() if value]
            results: list[EmailMessageData] = []
            allowed = set(allow_senders)
            excluded = set(exclude_senders)

            for uid in reversed(uids):
                message_data = self._fetch_message(connection, uid)
                if message_data is None:
                    continue
                if message_data.received_at < cutoff:
                    continue
                if message_data.sender_email in excluded:
                    continue
                results.append(message_data)
                if len(results) >= max_messages:
                    break

            return results
        finally:
            try:
                connection.close()
            except Exception:
                pass
            try:
                connection.logout()
            except Exception:
                pass

    def _fetch_message(
        self,
        connection: imaplib.IMAP4_SSL,
        uid: str,
    ) -> EmailMessageData | None:
        status, fetched = connection.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
            return None

        message = message_from_bytes(fetched[0][1])
        sender = self._decode_header_value(message.get("From", "Unknown sender"))
        sender_email = parseaddr(sender)[1].lower()
        subject = self._decode_header_value(message.get("Subject", "(No subject)"))
        email_id = message.get("Message-ID", uid).strip() or uid
        received_at = _parse_received_at(message.get("Date"))
        body = self._extract_body(message)
        return EmailMessageData(
            uid=uid,
            email_id=email_id,
            sender=sender,
            sender_email=sender_email,
            subject=subject,
            date=received_at.date().isoformat(),
            received_at=received_at,
            body=body,
        )

    def _decode_header_value(self, value: str) -> str:
        try:
            return str(make_header(decode_header(value))).strip()
        except Exception:
            return value.strip()

    def _extract_body(self, message: Message) -> str:
        if message.is_multipart():
            parts = [
                part
                for part in message.walk()
                if part.get_content_maintype() == "text"
                and "attachment" not in (part.get("Content-Disposition", "").lower())
            ]
            plain_parts = [part for part in parts if part.get_content_subtype() == "plain"]
            chosen_parts = plain_parts or parts
            text = "\n\n".join(self._decode_part(part) for part in chosen_parts)
        else:
            text = self._decode_part(message)

        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _decode_part(self, part: Message) -> str:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except LookupError:
            decoded = payload.decode("utf-8", errors="replace")
        if part.get_content_subtype() == "html":
            decoded = _html_to_text(decoded)
        return decoded


def _parse_received_at(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now(timezone.utc)
    parsed = parsedate_to_datetime(raw_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"[ \t]+", " ", text)
