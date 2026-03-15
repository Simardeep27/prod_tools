from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os

import yaml


DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"


@dataclass(frozen=True)
class ScheduleConfig:
    timezone: str
    times: list[str]
    launchd_label: str


@dataclass(frozen=True)
class EmailFilterConfig:
    mailbox: str
    unread_only: bool
    lookback_hours: int
    max_messages: int
    max_body_chars: int
    allow_senders: list[str]
    exclude_senders: list[str]


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    max_tokens: int


@dataclass(frozen=True)
class TaskPromptConfig:
    description: str
    output_file: Path


@dataclass(frozen=True)
class AppConfig:
    schedule: ScheduleConfig
    email: EmailFilterConfig
    llm: LLMConfig
    categorization_task: TaskPromptConfig
    reporting_task: TaskPromptConfig


def default_env_path(project_root: Path) -> Path | None:
    candidates = [project_root / ".env", project_root.parent / ".env"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_dotenv(env_path: Path | None) -> None:
    if env_path is None or not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def load_app_config(config_path: Path, project_root: Path) -> AppConfig:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    schedule_raw = raw.get("schedule", {})
    email_raw = raw.get("email", {})
    llm_raw = raw.get("llm", {})

    times = [_normalize_time(value) for value in schedule_raw.get("times", ["08:00"])]
    return AppConfig(
        schedule=ScheduleConfig(
            timezone=str(schedule_raw.get("timezone", "America/New_York")),
            times=times,
            launchd_label=str(schedule_raw.get("launchd_label", "com.example.email-auto")),
        ),
        email=EmailFilterConfig(
            mailbox=str(email_raw.get("mailbox", "INBOX")),
            unread_only=_coerce_bool(email_raw.get("unread_only", True)),
            lookback_hours=int(email_raw.get("lookback_hours", 24)),
            max_messages=int(email_raw.get("max_messages", 20)),
            max_body_chars=int(email_raw.get("max_body_chars", 6000)),
            allow_senders=_normalize_senders(email_raw.get("allow_senders", [])),
            exclude_senders=_normalize_senders(email_raw.get("exclude_senders", [])),
        ),
        llm=LLMConfig(
            provider=str(llm_raw.get("provider", "mlx_lm")),
            model=os.environ.get("EMAIL_AUTO_MODEL", str(llm_raw.get("model", DEFAULT_MODEL))),
            max_tokens=int(llm_raw.get("max_tokens", 1200)),
        ),
        categorization_task=_load_task(raw, "categorization_task", project_root),
        reporting_task=_load_task(raw, "reporting_task", project_root),
    )


def _load_task(raw: dict[str, Any], key: str, project_root: Path) -> TaskPromptConfig:
    task_raw = raw.get(key, {})
    description = str(task_raw.get("description", "")).strip()
    if not description:
        raise ValueError(f"{key}.description is required")
    output_file = project_root / str(task_raw.get("output_file", f"output/{key}.txt"))
    return TaskPromptConfig(description=description, output_file=output_file)


def _normalize_time(value: Any) -> str:
    time_text = str(value).strip()
    parts = time_text.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid schedule time: {time_text}")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour not in range(24) or minute not in range(60):
        raise ValueError(f"Invalid schedule time: {time_text}")
    return f"{hour:02d}:{minute:02d}"


def _normalize_senders(values: Any) -> list[str]:
    if not values:
        return []
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
