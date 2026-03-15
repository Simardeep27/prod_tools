from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from email_auto.config import default_env_path, load_app_config, load_dotenv
from email_auto.email_client import load_email_credentials
from email_auto.pipeline import EmailAutomationPipeline, RunArtifacts
from email_auto.scheduler import write_launch_agent_plist


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = DEFAULT_PROJECT_ROOT / "src" / "email_auto" / "config" / "tasks.yaml"


@dataclass
class EmailAuto:
    config_path: Path = DEFAULT_CONFIG_PATH
    env_path: Path | None = None

    def _resolved_env_path(self) -> Path | None:
        if self.env_path is not None:
            return self.env_path
        return default_env_path(DEFAULT_PROJECT_ROOT)

    def _load_config(self):
        env_path = self._resolved_env_path()
        load_dotenv(env_path)
        return load_app_config(self.config_path, DEFAULT_PROJECT_ROOT)

    def run_once(self, force: bool = False, limit: int | None = None) -> RunArtifacts:
        config = self._load_config()
        credentials = load_email_credentials()
        pipeline = EmailAutomationPipeline(
            config=config,
            project_root=DEFAULT_PROJECT_ROOT,
            credentials=credentials,
        )
        return pipeline.run_once(force=force, limit=limit)

    def write_launchd_plist(
        self,
        output_path: Path | None = None,
        python_path: Path | None = None,
        working_dir: Path | None = None,
        label: str | None = None,
    ) -> Path:
        config = self._load_config()
        env_path = self._resolved_env_path()
        return write_launch_agent_plist(
            config=config,
            config_path=self.config_path,
            output_path=output_path,
            python_path=python_path,
            working_dir=working_dir or DEFAULT_PROJECT_ROOT,
            env_path=env_path,
            label=label,
        )
