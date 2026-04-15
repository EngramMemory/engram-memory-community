"""Installer that wires the bridge into Claude Code's SessionStart hook.

Design goals:
- Idempotent. Running the installer twice must leave settings.json in
  the same shape as running it once.
- Safe. We back up the existing settings.json before writing.
- Minimal. We only touch the ``hooks.SessionStart`` array and only add
  our own entry; existing entries are preserved untouched.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
HOOK_MARKER = "engram-bridge-pull"
HOOK_COMMAND = "engram bridge pull"


@dataclass
class InstallResult:
    settings_path: Path
    backup_path: Optional[Path]
    changed: bool
    action: str  # "added", "already-installed", "created-settings"
    message: str


def _load_settings(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + ".bak-" + stamp)
    shutil.copy2(path, backup)
    return backup


def _hook_entry() -> Dict[str, Any]:
    """Shape of the hook entry we register.

    Claude Code's settings.json supports a ``hooks`` section where each
    event (``SessionStart``, ``PostToolUse``, ...) maps to a list of
    matchers. Each matcher is ``{matcher, hooks: [{type, command}]}``.
    We register a single command hook that runs on every session start
    regardless of matcher.
    """
    return {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": HOOK_COMMAND,
                "id": HOOK_MARKER,
            }
        ],
    }


def _already_installed(session_start: List[Any]) -> bool:
    for item in session_start:
        if not isinstance(item, dict):
            continue
        hooks = item.get("hooks") or []
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            if hook.get("id") == HOOK_MARKER:
                return True
            cmd = hook.get("command")
            if isinstance(cmd, str) and cmd.strip() == HOOK_COMMAND:
                return True
    return False


def install_claude_code_hook(
    settings_path: Optional[Path] = None,
) -> InstallResult:
    """Patch ``~/.claude/settings.json`` to register our SessionStart hook.

    Safe to call repeatedly. Returns an ``InstallResult`` describing what
    happened.
    """
    target = settings_path or CLAUDE_SETTINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    existed = target.exists()
    settings = _load_settings(target)

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    session_start = hooks.get("SessionStart")
    if not isinstance(session_start, list):
        session_start = []

    if _already_installed(session_start):
        return InstallResult(
            settings_path=target,
            backup_path=None,
            changed=False,
            action="already-installed",
            message="SessionStart hook already registered.",
        )

    backup = _backup(target) if existed else None

    session_start.append(_hook_entry())
    hooks["SessionStart"] = session_start
    settings["hooks"] = hooks

    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    tmp.replace(target)

    action = "added" if existed else "created-settings"
    message = "Registered SessionStart hook in {}".format(target)
    if backup:
        message += " (backup: {})".format(backup.name)
    return InstallResult(
        settings_path=target,
        backup_path=backup,
        changed=True,
        action=action,
        message=message,
    )
