from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from json import JSONDecoder
from pathlib import Path
from typing import Any
import json

from zoneinfo import ZoneInfo

from email_auto.config import AppConfig
from email_auto.email_client import EmailCredentials, EmailMessageData, IMAPEmailClient
from email_auto.llm import MlxLMClient


CATEGORY_VALUES = {
    "JOB/INTERNSHIP",
    "UNIVERSITY",
    "PERSONAL",
    "PAYMENTS/TRANSACTIONS",
    "OTHER",
}
PRIORITY_VALUES = {"HIGH", "MEDIUM", "LOW"}
ACTION_VALUES = {"REPLY", "READ_ONLY", "TASK", "IGNORE"}


@dataclass(frozen=True)
class RunArtifacts:
    processed_count: int
    summary_path: Path
    categorization_path: Path
    run_directory: Path


class EmailAutomationPipeline:
    def __init__(
        self,
        config: AppConfig,
        project_root: Path,
        credentials: EmailCredentials,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.credentials = credentials
        self.client = IMAPEmailClient(credentials)
        self.state_path = project_root / "state" / "runtime_state.json"
        self.logs_dir = project_root / "logs"

    def run_once(self, force: bool = False, limit: int | None = None) -> RunArtifacts:
        self._ensure_directories()
        state = self._load_state()
        now = datetime.now(ZoneInfo(self.config.schedule.timezone))
        run_stamp = now.strftime("%Y%m%d_%H%M%S")
        run_directory = self.project_root / "output" / "runs" / run_stamp
        run_directory.mkdir(parents=True, exist_ok=True)

        max_messages = limit or self.config.email.max_messages
        emails = self.client.fetch_recent_emails(
            mailbox=self.config.email.mailbox,
            unread_only=self.config.email.unread_only,
            lookback_hours=self.config.email.lookback_hours,
            max_messages=max_messages,
            allow_senders=self.config.email.allow_senders,
            exclude_senders=self.config.email.exclude_senders,
        )
        fetched_payload = [email.to_prompt_payload() for email in emails]
        self._write_json(run_directory / "fetched_emails.json", fetched_payload)

        processed_uids = set(state.get("processed_uids", []))
        selected = emails if force else [email for email in emails if email.uid not in processed_uids]

        if not selected:
            summary = self._empty_summary(now)
            report = {"generated_at": now.isoformat(), "emails": []}
            self._persist_reports(report, summary, run_directory)
            state["last_run_at"] = now.isoformat()
            self._save_state(state)
            return RunArtifacts(
                processed_count=0,
                summary_path=self.config.reporting_task.output_file,
                categorization_path=self.config.categorization_task.output_file,
                run_directory=run_directory,
            )

        llm = MlxLMClient(
            model_name=self.config.llm.model,
            default_max_tokens=self.config.llm.max_tokens,
        )
        categorized = [self._categorize_email(llm, email) for email in selected]
        summary = self._summarize(llm, categorized, now)
        report = {
            "generated_at": now.isoformat(),
            "mailbox": self.config.email.mailbox,
            "model": self.config.llm.model,
            "emails": categorized,
        }
        self._persist_reports(report, summary, run_directory)

        state["last_run_at"] = now.isoformat()
        state["processed_uids"] = self._merge_processed_uids(processed_uids, selected)
        self._save_state(state)
        return RunArtifacts(
            processed_count=len(categorized),
            summary_path=self.config.reporting_task.output_file,
            categorization_path=self.config.categorization_task.output_file,
            run_directory=run_directory,
        )

    def _categorize_email(self, llm: MlxLMClient, email: EmailMessageData) -> dict[str, Any]:
        trimmed_body = email.body[: self.config.email.max_body_chars]
        messages = [
            {
                "role": "system",
                "content": "You analyze emails and must respond with valid JSON only.",
            },
            {
                "role": "user",
                "content": (
                    f"{self.config.categorization_task.description}\n\n"
                    f"EMAIL:\n{json.dumps({**email.to_prompt_payload(), 'body': trimmed_body}, indent=2)}"
                ),
            },
        ]
        raw_response = llm.complete(messages)
        try:
            parsed = extract_json_payload(raw_response)
        except ValueError:
            parsed = {}

        key_points = parsed.get("key_points")
        if not isinstance(key_points, list):
            key_points = [point for point in [str(parsed.get("recommended_next_step", "")).strip()] if point]
        print(parsed)
        return {
            "email_id": parsed.get("email_id") or email.email_id,
            "subject": parsed.get("subject") or email.subject,
            "sender": parsed.get("sender") or email.sender,
            "category": _normalize_choice(parsed.get("category"), CATEGORY_VALUES, "OTHER"),
            "priority": _normalize_choice(parsed.get("priority"), PRIORITY_VALUES, "LOW"),
            "required_action": _normalize_choice(parsed.get("required_action"), ACTION_VALUES, "READ_ONLY"),
            "date": parsed.get("date") or email.date,
            "deadline": parsed.get("deadline"),
            "key_points": [str(point).strip() for point in key_points if str(point).strip()],
            "recommended_next_step": str(
                parsed.get("recommended_next_step") or "Review manually."
            ).strip(),
            "body_preview": trimmed_body[:400],
        }

    def _summarize(
        self,
        llm: MlxLMClient,
        categorized: list[dict[str, Any]],
        now: datetime,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": "You create concise Markdown email digests and return Markdown only.",
            },
            {
                "role": "user",
                "content": (
                    f"{self.config.reporting_task.description}\n\n"
                    f"RUN_TIME: {now.isoformat()}\n"
                    f"EMAILS:\n{json.dumps(categorized, indent=2)}"
                ),
            },
        ]
        return llm.complete(messages)

    def _persist_reports(self, report: dict[str, Any], summary: str, run_directory: Path) -> None:
        self._write_json(run_directory / "categorization_report.json", report)
        self._write_text(run_directory / "daily_summary.md", summary)
        self._write_json(self.config.categorization_task.output_file, report)
        self._write_text(self.config.reporting_task.output_file, summary)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_path, state)

    def _merge_processed_uids(
        self,
        existing: set[str],
        emails: list[EmailMessageData],
    ) -> list[str]:
        merged = list(existing.union({email.uid for email in emails}))
        return sorted(merged)[-5000:]

    def _ensure_directories(self) -> None:
        for path in [
            self.project_root / "output" / "runs",
            self.project_root / "state",
            self.logs_dir,
            self.config.categorization_task.output_file.parent,
            self.config.reporting_task.output_file.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_text(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload.strip() + "\n", encoding="utf-8")

    def _empty_summary(self, now: datetime) -> str:
        return (
            f"# Daily Email Summary\n\n"
            f"Generated: {now.isoformat()}\n\n"
            "No new emails matched the configured window.\n"
        )


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    decoder = JSONDecoder()
    text = raw_text.strip()
    for start in range(len(text)):
        if text[start] not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
        raise ValueError("Expected JSON object")
    raise ValueError("No JSON object found in model output")


def _normalize_choice(value: Any, allowed: set[str], fallback: str) -> str:
    candidate = str(value or "").strip().upper()
    return candidate if candidate in allowed else fallback
