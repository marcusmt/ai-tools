import os
import stat
import sys
import tomllib
from importlib import resources
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


_PLACEHOLDERS = {
    "your-org.atlassian.net",
    "you@example.com",
    "your-jira-token-here",
    "your-gcp-project",
}


class JiraConfig(BaseModel):
    url: str
    user: str
    token: str


class LLMOverride(BaseModel):
    command: Optional[str] = None
    model: Optional[str] = None
    env: Optional[dict[str, str]] = None


class LLMGlobalConfig(BaseModel):
    command: str
    model: str
    env: dict[str, str]
    analyze: LLMOverride = LLMOverride()
    investigate: LLMOverride = LLMOverride()
    plan: LLMOverride = LLMOverride()


class LLMConfig(BaseModel):
    command: str
    model: str
    env: dict[str, str]


class Config(BaseModel):
    jira: JiraConfig
    llm: LLMGlobalConfig


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "task-builder" / "config.toml"


def _check_permissions(path: Path) -> None:
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(f"Warning: {path} has loose permissions. Run: chmod 600 {path}", file=sys.stderr)


def _check_placeholders(raw: dict) -> None:
    text = str(raw)
    found = [p for p in _PLACEHOLDERS if p in text]
    if found:
        raise SystemExit(
            f"Config contains placeholder values. "
            f"Edit {config_path()} and replace placeholders with real values."
        )


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        raise SystemExit(
            f"Config not found at {path}. Run `task-builder install` to create it."
        )
    _check_permissions(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    _check_placeholders(raw)
    try:
        return Config.model_validate(raw)
    except Exception as e:
        raise SystemExit(f"Config is invalid: {e}") from e


def get_llm_config(config: Config, stage: str, model_override: Optional[str] = None) -> LLMConfig:
    g = config.llm
    override: LLMOverride = getattr(g, stage, LLMOverride())
    resolved = LLMConfig(
        command=override.command if override.command is not None else g.command,
        model=override.model if override.model is not None else g.model,
        env=override.env if override.env is not None else g.env,
    )
    if model_override is not None:
        resolved = resolved.model_copy(update={"model": model_override})
    return resolved


def get_jira_config(config: Config) -> JiraConfig:
    return config.jira


def install_config() -> None:
    path = config_path()
    if path.exists():
        print(f"Config already exists at {path}. Edit it to update credentials.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    example = resources.files("jira_triage").joinpath("config.example.toml")
    path.write_bytes(example.read_bytes())
    path.chmod(0o600)
    print(f"Config created at {path}")
    print("Edit it and replace placeholder values before running other commands.")
