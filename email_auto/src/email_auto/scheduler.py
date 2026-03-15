from __future__ import annotations

from pathlib import Path
import plistlib
import sys

from email_auto.config import AppConfig


def write_launch_agent_plist(
    config: AppConfig,
    config_path: Path,
    output_path: Path | None,
    python_path: Path | None,
    working_dir: Path,
    env_path: Path | None,
    label: str | None = None,
) -> Path:
    logs_dir = working_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    plist = build_launch_agent_plist(
        config=config,
        config_path=config_path,
        python_path=python_path or Path(sys.executable),
        working_dir=working_dir,
        env_path=env_path,
        label=label or config.schedule.launchd_label,
        logs_dir=logs_dir,
    )
    target = output_path or working_dir / "launchd" / f"{plist['Label']}.plist"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)
    return target


def build_launch_agent_plist(
    config: AppConfig,
    config_path: Path,
    python_path: Path,
    working_dir: Path,
    env_path: Path | None,
    label: str,
    logs_dir: Path,
) -> dict[str, object]:
    intervals = [_calendar_interval(value) for value in config.schedule.times]
    start_calendar = intervals[0] if len(intervals) == 1 else intervals
    args = [
        str(python_path),
        "-m",
        "email_auto.main",
        "run",
        "--config",
        str(config_path),
    ]
    if env_path is not None:
        args.extend(["--env-file", str(env_path)])

    return {
        "Label": label,
        "ProgramArguments": args,
        "WorkingDirectory": str(working_dir),
        "StartCalendarInterval": start_calendar,
        "StandardOutPath": str(logs_dir / "email_auto.stdout.log"),
        "StandardErrorPath": str(logs_dir / "email_auto.stderr.log"),
    }


def _calendar_interval(value: str) -> dict[str, int]:
    hour_text, minute_text = value.split(":")
    return {"Hour": int(hour_text), "Minute": int(minute_text)}
