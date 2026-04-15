"""Config loading and validation for the Engram Bridge.

Contract: if anything is wrong with the config, return a ``BridgeConfig``
with ``enabled = False`` and a human-readable ``reason``. Never raise.
Callers decide how to react to a disabled bridge (almost always: exit 0
silently).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


CONFIG_DIR = Path.home() / ".engram"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
LOG_PATH = CONFIG_DIR / "bridge.log"

DEFAULT_API_BASE = "https://api.engrammemory.ai"
DEFAULT_TOP_K = 8
API_KEY_PREFIX = "eng_live_"

CONFIG_TEMPLATE = """# Engram Bridge configuration.
#
# Leave api_key empty to keep the bridge disabled. When disabled, all
# bridge commands exit silently — they will never break your workflow.
#
# To activate:
#   1. Grab an API key from https://engrammemory.ai
#   2. Paste it below (it will start with eng_live_)
#   3. Run `engram bridge status` to confirm it's live

api_key: ""
api_base: "https://api.engrammemory.ai"
enabled: true

projects:
  default:
    top_k: 8
  # Example project override — match by project_id (usually the git repo
  # basename). Uncomment and edit to use.
  #
  # my-repo:
  #   top_k: 12
"""


@dataclass
class ProjectConfig:
    """Per-project overrides. Missing fields fall back to defaults."""

    top_k: int = DEFAULT_TOP_K


@dataclass
class BridgeConfig:
    """Result of loading ``~/.engram/config.yaml``.

    When ``enabled`` is False, ``reason`` explains why in one short line
    suitable for `engram bridge status` or the log.
    """

    enabled: bool
    reason: str = ""
    api_key: str = ""
    api_base: str = DEFAULT_API_BASE
    config_path: Path = field(default_factory=lambda: CONFIG_PATH)
    projects: Dict[str, ProjectConfig] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def top_k_for(self, project_id: str) -> int:
        """Return top_k for the given project, falling back to default."""
        if project_id in self.projects:
            return self.projects[project_id].top_k
        if "default" in self.projects:
            return self.projects["default"].top_k
        return DEFAULT_TOP_K


def _disabled(reason: str, path: Optional[Path] = None) -> BridgeConfig:
    return BridgeConfig(
        enabled=False,
        reason=reason,
        config_path=path or CONFIG_PATH,
    )


def load_config(path: Optional[Path] = None) -> BridgeConfig:
    """Load and validate the bridge config.

    Never raises. Returns a ``BridgeConfig`` whose ``enabled`` field is
    the single source of truth for whether the bridge should do anything.
    """
    config_path = path or CONFIG_PATH

    if not config_path.exists():
        return _disabled("no config file at {}".format(config_path), config_path)

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        return _disabled(
            "config file unreadable: {}".format(exc), config_path
        )

    if not isinstance(raw, dict):
        return _disabled("config root is not a mapping", config_path)

    enabled_flag = raw.get("enabled", True)
    if enabled_flag is False:
        return _disabled("enabled: false in config", config_path)

    api_key = raw.get("api_key") or ""
    if not isinstance(api_key, str):
        api_key = ""
    api_key = api_key.strip()

    if not api_key:
        return _disabled("api_key empty", config_path)

    if not api_key.startswith(API_KEY_PREFIX):
        return _disabled(
            "api_key does not start with {}".format(API_KEY_PREFIX),
            config_path,
        )

    api_base = raw.get("api_base") or DEFAULT_API_BASE
    if not isinstance(api_base, str) or not api_base.strip():
        api_base = DEFAULT_API_BASE
    api_base = api_base.rstrip("/")

    projects: Dict[str, ProjectConfig] = {}
    projects_raw = raw.get("projects") or {}
    if isinstance(projects_raw, dict):
        for name, value in projects_raw.items():
            if not isinstance(name, str):
                continue
            pc = ProjectConfig()
            if isinstance(value, dict):
                top_k = value.get("top_k")
                if isinstance(top_k, int) and top_k > 0:
                    pc.top_k = top_k
            projects[name] = pc

    return BridgeConfig(
        enabled=True,
        reason="",
        api_key=api_key,
        api_base=api_base,
        config_path=config_path,
        projects=projects,
        raw=raw,
    )


def ensure_config_dir() -> Path:
    """Create ``~/.engram/`` if it doesn't exist. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    return CONFIG_DIR


def write_config_template(path: Optional[Path] = None) -> Path:
    """Create a config template at the target path if it doesn't exist.

    Does not overwrite. Returns the path either way.
    """
    target = path or CONFIG_PATH
    ensure_config_dir()
    if not target.exists():
        target.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return target


def log_path() -> Path:
    """Return the log path, ensuring the parent dir exists."""
    ensure_config_dir()
    return LOG_PATH
