from __future__ import annotations

import argparse
from pathlib import Path

from email_auto.crew import EmailAuto


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = DEFAULT_PROJECT_ROOT / "src" / "email_auto" / "config" / "tasks.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="email_auto",
        description="Fetch emails, classify them, and generate a local daily digest.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Fetch recent emails and build the digest.")
    run_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    run_parser.add_argument("--env-file", type=Path)
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--force", action="store_true")

    launchd_parser = subparsers.add_parser(
        "write-launchd",
        help="Write a launchd plist using the schedule defined in tasks.yaml.",
    )
    launchd_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    launchd_parser.add_argument("--env-file", type=Path)
    launchd_parser.add_argument("--output", type=Path)
    launchd_parser.add_argument("--python-path", type=Path)
    launchd_parser.add_argument("--working-dir", type=Path, default=DEFAULT_PROJECT_ROOT)
    launchd_parser.add_argument("--label")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"
    service = EmailAuto(config_path=args.config, env_path=getattr(args, "env_file", None))

    if command == "write-launchd":
        output_path = service.write_launchd_plist(
            output_path=args.output,
            python_path=args.python_path,
            working_dir=args.working_dir,
            label=args.label,
        )
        print(output_path)
        return 0

    result = service.run_once(force=args.force, limit=args.limit)
    print(f"Processed {result.processed_count} email(s). Summary: {result.summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
