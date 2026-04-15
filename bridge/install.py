"""Installers that wire the bridge into outside systems.

Two surfaces today:

1. Claude Code's ``SessionStart`` hook — patches
   ``~/.claude/settings.json`` so every new agent session runs
   ``engram bridge pull`` and gets the pulled memories as prompt
   context. (Wave 1.)

2. A git ``post-commit`` hook — writes ``.git/hooks/post-commit`` in
   the target repo so every commit calls
   ``engram-bridge push-commit``, feeding new commits into Engram's
   cloud memory without any manual action. (Wave 2.)

Shared design goals:

- **Idempotent.** Running an installer twice leaves the target in the
  same shape as running it once.
- **Safe.** We take a timestamped backup of any file we modify before
  writing new content.
- **Minimal.** We only touch our own markers. Existing hook logic and
  existing settings entries are preserved.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
HOOK_MARKER = "engram-bridge-pull"
HOOK_COMMAND = "engram bridge pull"

# ---------------------------------------------------------------------
# Git post-commit hook constants
# ---------------------------------------------------------------------

GIT_HOOK_MARKER = "# engram-bridge: push-commit"
GIT_HOOK_COMMAND = "engram-bridge push-commit >/dev/null 2>&1 || true"
GIT_HOOK_SCRIPT = (
    "#!/bin/sh\n"
    "{marker}\n"
    "{command}\n"
).format(marker=GIT_HOOK_MARKER, command=GIT_HOOK_COMMAND)


@dataclass
class InstallResult:
    settings_path: Path
    backup_path: Optional[Path]
    changed: bool
    action: str  # "added", "already-installed", "created-settings"
    message: str


@dataclass
class InstallOutcome:
    """Result of installing a git hook into a target repo.

    ``action`` values:
      - ``"created"`` — .git/hooks/post-commit did not exist; we wrote it
      - ``"merged"`` — hook already existed; we appended our command
      - ``"already-installed"`` — our marker was already present, no-op
      - ``"no-repo"`` — the target directory is not a git repo
    """

    hook_path: Path
    backup_path: Optional[Path]
    changed: bool
    action: str
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


# ---------------------------------------------------------------------
# Git post-commit hook installer (Wave 2)
# ---------------------------------------------------------------------


def _resolve_git_dir(repo_dir: Path) -> Optional[Path]:
    """Return the directory that holds ``hooks/`` for this repo.

    Handles plain repos, worktrees, and repos with a gitdir link file
    by trusting ``git rev-parse --git-common-dir`` when available and
    falling back to a plain ``.git`` check. Returns ``None`` when the
    target isn't a git repo we can work with.
    """
    if not repo_dir.exists():
        return None

    # Prefer git itself so we handle worktrees correctly.
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        result = None

    if result is not None and result.returncode == 0:
        raw = (result.stdout or "").strip()
        if raw:
            path = Path(raw)
            if not path.is_absolute():
                path = (repo_dir / path).resolve()
            if path.is_dir():
                return path

    dot_git = repo_dir / ".git"
    if dot_git.is_dir():
        return dot_git
    return None


def _ensure_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def _git_hook_already_installed(text: str) -> bool:
    return GIT_HOOK_MARKER in text


def _merge_hook(existing: str) -> str:
    """Append our marker+command block to an existing post-commit hook.

    We preserve the original script verbatim (including its shebang)
    and add a clearly-marked trailing block so future invocations can
    find the marker and no-op.
    """
    body = existing.rstrip() + "\n"
    block = (
        "\n"
        "{marker}\n"
        "{command}\n"
    ).format(marker=GIT_HOOK_MARKER, command=GIT_HOOK_COMMAND)
    return body + block


def install_git_hooks(repo_dir: str) -> InstallOutcome:
    """Install a post-commit hook into ``repo_dir``.

    Writes ``.git/hooks/post-commit`` with our marker comment and the
    ``engram-bridge push-commit`` call. If a hook already exists we
    keep it and append our block. If our marker is already present we
    do nothing. All existing content is backed up to
    ``post-commit.bak-<timestamp>`` first.

    The hook command uses ``|| true`` so a missing or broken
    ``engram-bridge`` binary can never block a commit.
    """
    target_repo = Path(repo_dir).expanduser().resolve()
    git_dir = _resolve_git_dir(target_repo)
    if git_dir is None:
        return InstallOutcome(
            hook_path=target_repo / ".git" / "hooks" / "post-commit",
            backup_path=None,
            changed=False,
            action="no-repo",
            message="Not a git repo: {}".format(target_repo),
        )

    hooks_dir = git_dir / "hooks"
    try:
        hooks_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return InstallOutcome(
            hook_path=hooks_dir / "post-commit",
            backup_path=None,
            changed=False,
            action="no-repo",
            message="Could not create hooks dir: {}".format(exc),
        )

    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        try:
            existing = hook_path.read_text(encoding="utf-8")
        except OSError as exc:
            return InstallOutcome(
                hook_path=hook_path,
                backup_path=None,
                changed=False,
                action="no-repo",
                message="Could not read existing hook: {}".format(exc),
            )

        if _git_hook_already_installed(existing):
            _ensure_executable(hook_path)
            return InstallOutcome(
                hook_path=hook_path,
                backup_path=None,
                changed=False,
                action="already-installed",
                message=(
                    "post-commit hook already wired to engram-bridge "
                    "at {}".format(hook_path)
                ),
            )

        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup_path = hook_path.with_name(
            "post-commit.bak-{}".format(stamp)
        )
        try:
            shutil.copy2(hook_path, backup_path)
        except OSError as exc:
            return InstallOutcome(
                hook_path=hook_path,
                backup_path=None,
                changed=False,
                action="no-repo",
                message="Could not back up hook: {}".format(exc),
            )

        merged = _merge_hook(existing)
        tmp = hook_path.with_name("post-commit.tmp")
        try:
            tmp.write_text(merged, encoding="utf-8")
            tmp.replace(hook_path)
        except OSError as exc:
            return InstallOutcome(
                hook_path=hook_path,
                backup_path=backup_path,
                changed=False,
                action="no-repo",
                message="Could not write hook: {}".format(exc),
            )
        _ensure_executable(hook_path)
        return InstallOutcome(
            hook_path=hook_path,
            backup_path=backup_path,
            changed=True,
            action="merged",
            message=(
                "Merged engram-bridge into existing post-commit hook "
                "at {} (backup: {})"
            ).format(hook_path, backup_path.name),
        )

    # Fresh install.
    tmp = hook_path.with_name("post-commit.tmp")
    try:
        tmp.write_text(GIT_HOOK_SCRIPT, encoding="utf-8")
        tmp.replace(hook_path)
    except OSError as exc:
        return InstallOutcome(
            hook_path=hook_path,
            backup_path=None,
            changed=False,
            action="no-repo",
            message="Could not write hook: {}".format(exc),
        )
    _ensure_executable(hook_path)
    return InstallOutcome(
        hook_path=hook_path,
        backup_path=None,
        changed=True,
        action="created",
        message="Created post-commit hook at {}".format(hook_path),
    )
