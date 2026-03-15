# Email Auto

`email_auto` is a local daily inbox digest pipeline:

1. Fetch recent emails over IMAP.
2. Classify each message with a local LLM using the prompt rules in `src/email_auto/config/tasks.yaml`.
3. Write a structured JSON report plus a Markdown digest.
4. Generate a `launchd` plist so macOS can run it on a schedule.

The default runtime is designed for Apple Silicon with `mlx-lm`.

## Setup

Install the package dependencies:

```bash
cd email_auto
uv sync
uv add mlx-lm
```

Create a local env file:

```bash
cp ../.env.example .env
```

Required env vars:

```bash
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
EMAIL_ACCOUNT=you@example.com
EMAIL_PASSWORD=your-app-password
```

Use an app password for Gmail, not your normal account password.

## Config

Edit `src/email_auto/config/tasks.yaml` to control:

- the daily run times
- mailbox filtering
- the local model id
- the classification rules
- the final Markdown summary instructions

## Run Once

```bash
cd email_auto
uv run email_auto run
```

Outputs are written to:

- `output/categorization_report.json`
- `output/daily_summary.md`
- `output/runs/<timestamp>/...`
- `state/runtime_state.json`

## Schedule on macOS

Generate a plist from the schedule in `tasks.yaml`:

```bash
cd email_auto
uv run email_auto write-launchd --output ~/Library/LaunchAgents/com.prodtools.email-auto.plist
```

Load it with:

```bash
launchctl unload ~/Library/LaunchAgents/com.prodtools.email-auto.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.prodtools.email-auto.plist
```

The job runs at the `schedule.times` values in `tasks.yaml` and writes logs into `logs/`.
