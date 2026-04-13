"""Event-driven push path for the Engram Bridge.

Wave 2 scope: turn meaningful local events (manual milestones, git
commits, green test suites) into memories on the cloud. Everything in
this module obeys the same contract as Wave 1's read path:

- **Off unless configured.** If ``load_config()`` returns a disabled
  ``BridgeConfig``, every push helper silently returns a ``skipped``
  outcome and exits without touching the network.
- **Never raises.** All network and I/O failures are caught, logged,
  and swallowed. Callers (CLI, git hook, pytest plugin) can safely
  treat this module as "best effort, never break my workflow".
- **Writes to ``~/.engram/bridge.log``** — same rotating handler Wave 1
  already set up in ``pull.py``. Stdout stays clean so a failing push
  can never leak into a shell or a CI log.

The public surface is three functions plus one result dataclass:

    push_manual(message, push_type="milestone", metadata=None)
    push_git_commit(repo_dir)
    push_test_pass(suite_name, duration, test_count, runner)
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from .client import EngramClient
from .config import BridgeConfig, load_config, log_path
from .project import ProjectContext, detect_project


_LOGGER_NAME = "engram.bridge.push"
_logger_configured = False


# Canonical event type strings. Stored in metadata["event_type"] so the
# cloud side can filter/aggregate by kind without parsing free text.
EVENT_MANUAL = "milestone"
EVENT_COMMIT = "commit"
EVENT_TEST_PASS = "test_pass"


def _get_logger() -> logging.Logger:
    """Rotating-file logger shared by every push helper.

    Uses the same ``~/.engram/bridge.log`` file Wave 1's pull path
    writes to. We configure our own handler (not the pull logger's)
    because ``_logger_configured`` is per-module and we want push
    entries to include the ``engram.bridge.push`` name for grepping.
    """
    global _logger_configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _logger_configured:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        handler = RotatingFileHandler(
            str(log_path()),
            maxBytes=256_000,
            backupCount=2,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s"
            )
        )
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    _logger_configured = True
    return logger


@dataclass
class PushOutcome:
    """Result of a push attempt.

    ``status`` is one of:
      - ``"disabled"`` — bridge off, no network call made
      - ``"sent"`` — API returned 2xx, we have a memory id
      - ``"failed"`` — network/HTTP/parse error, see ``reason``
      - ``"skipped"`` — nothing to push (e.g. empty commit)
    """

    status: str
    event_type: str
    reason: str = ""
    memory_id: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "sent"


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _disabled_outcome(event_type: str, reason: str) -> PushOutcome:
    _get_logger().info("push skipped (%s): %s", event_type, reason)
    return PushOutcome(
        status="disabled", event_type=event_type, reason=reason
    )


def _skipped_outcome(event_type: str, reason: str) -> PushOutcome:
    _get_logger().info("push nothing-to-do (%s): %s", event_type, reason)
    return PushOutcome(
        status="skipped", event_type=event_type, reason=reason
    )


def _failed_outcome(
    event_type: str,
    reason: str,
    payload: Optional[Dict[str, Any]] = None,
) -> PushOutcome:
    _get_logger().warning("push failed (%s): %s", event_type, reason)
    return PushOutcome(
        status="failed",
        event_type=event_type,
        reason=reason,
        payload=payload or {},
    )


def _sent_outcome(
    event_type: str,
    response: Dict[str, Any],
    payload: Dict[str, Any],
) -> PushOutcome:
    memory_id = None
    raw_id = response.get("id")
    if isinstance(raw_id, str) and raw_id:
        memory_id = raw_id
    _get_logger().info(
        "push sent (%s): memory_id=%s", event_type, memory_id or "?"
    )
    return PushOutcome(
        status="sent",
        event_type=event_type,
        reason="ok",
        memory_id=memory_id,
        response=response,
        payload=payload,
    )


def _project_metadata(proj: ProjectContext) -> Dict[str, Any]:
    """Stamp every push with the project context Wave 1 also uses.

    Keeping this consistent between read and write paths means that a
    pull can find memories created by a push from the same cwd — no
    separate join key needed on the cloud side.
    """
    md: Dict[str, Any] = {
        "project_id": proj.project_id,
        "cwd": str(proj.cwd),
    }
    if proj.repo_root is not None:
        md["repo_root"] = str(proj.repo_root)
    if proj.branch:
        md["branch"] = proj.branch
    return md


def _load_cfg_and_project(
    config: Optional[BridgeConfig],
    project: Optional[ProjectContext],
    cwd: Optional[Path] = None,
):
    cfg = config or load_config()
    proj = project or detect_project(cwd=cwd)
    return cfg, proj


def _push(
    event_type: str,
    content: str,
    metadata: Dict[str, Any],
    config: Optional[BridgeConfig] = None,
    project: Optional[ProjectContext] = None,
    cwd: Optional[Path] = None,
) -> PushOutcome:
    """Shared send path: check disabled, stamp metadata, POST store."""
    cfg, proj = _load_cfg_and_project(config, project, cwd)

    if not cfg.enabled:
        return _disabled_outcome(event_type, cfg.reason)

    stamped = dict(metadata or {})
    stamped.setdefault("event_type", event_type)
    stamped.setdefault("source", "engram-bridge")
    for key, value in _project_metadata(proj).items():
        stamped.setdefault(key, value)

    payload = {
        "content": content,
        "metadata": stamped,
        "classification": event_type,
    }

    client = EngramClient(cfg)
    try:
        response = client.store_memory(
            content=content,
            metadata=stamped,
            classification=event_type,
        )
    except Exception as exc:  # noqa: BLE001 — belt-and-suspenders
        return _failed_outcome(
            event_type, "store exception: {}".format(exc), payload
        )

    if response is None:
        return _failed_outcome(
            event_type, "store_memory returned None", payload
        )

    return _sent_outcome(event_type, response, payload)


# ---------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------


def _run_git(args: list, cwd: Path, timeout: float = 2.0) -> Optional[str]:
    """Run a git command, return stripped stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout or ""
    return out.strip() or None


def _commit_info(repo_dir: Path) -> Optional[Dict[str, Any]]:
    """Read last commit's sha, subject, and files-changed summary.

    Returns ``None`` if the directory isn't a git repo or has no
    commits yet — callers then produce a ``skipped`` outcome.
    """
    toplevel = _run_git(["rev-parse", "--show-toplevel"], repo_dir)
    if not toplevel:
        return None
    root = Path(toplevel)

    sha = _run_git(["rev-parse", "HEAD"], root)
    if not sha:
        return None
    short_sha = sha[:12]

    subject = _run_git(["log", "-1", "--pretty=%s"], root) or ""
    author = _run_git(["log", "-1", "--pretty=%an"], root) or ""
    body = _run_git(["log", "-1", "--pretty=%b"], root) or ""
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch == "HEAD":
        branch = None

    # ``git show --stat`` is human-friendly but bounded; truncate to
    # keep payloads small. We want ~300 chars of summary, not a full
    # diff dump.
    stat_raw = _run_git(
        ["show", "--stat", "--no-color", "--pretty=format:", sha], root
    ) or ""
    stat = stat_raw.strip()
    if len(stat) > 600:
        stat = stat[:600].rstrip() + "…"

    files_raw = _run_git(
        ["show", "--name-only", "--pretty=format:", sha], root
    ) or ""
    files = [line for line in files_raw.splitlines() if line.strip()]

    return {
        "sha": sha,
        "short_sha": short_sha,
        "subject": subject,
        "body": body,
        "author": author,
        "branch": branch,
        "stat": stat,
        "files": files,
        "repo_root": str(root),
    }


# ---------------------------------------------------------------------
# Public push helpers
# ---------------------------------------------------------------------


def push_manual(
    message: str,
    push_type: str = EVENT_MANUAL,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[BridgeConfig] = None,
    project: Optional[ProjectContext] = None,
) -> PushOutcome:
    """Push a hand-typed milestone or note.

    Used by the ``engram-bridge push`` CLI and by callers that want to
    mark "I just finished X" without any git or test context. A blank
    message short-circuits to ``skipped`` rather than writing an empty
    memory.
    """
    text = (message or "").strip()
    if not text:
        return _skipped_outcome(
            push_type or EVENT_MANUAL, "empty message"
        )

    md: Dict[str, Any] = dict(metadata or {})
    md.setdefault("manual", True)
    return _push(
        event_type=push_type or EVENT_MANUAL,
        content=text,
        metadata=md,
        config=config,
        project=project,
    )


def push_git_commit(
    repo_dir: str,
    config: Optional[BridgeConfig] = None,
) -> PushOutcome:
    """Push the current HEAD commit as a ``commit`` event.

    Called by the post-commit git hook we install with
    ``install.install_git_hooks``. Reads ``subject``, ``sha``, and
    ``git show --stat`` from the working repo; if there's no commit
    (new repo, detached work tree with nothing yet), returns
    ``skipped``.
    """
    repo_path = Path(repo_dir).expanduser().resolve()
    cfg = config or load_config()
    if not cfg.enabled:
        return _disabled_outcome(EVENT_COMMIT, cfg.reason)

    info = _commit_info(repo_path)
    if info is None:
        return _skipped_outcome(
            EVENT_COMMIT,
            "no commit info at {}".format(repo_path),
        )

    subject = info["subject"]
    short_sha = info["short_sha"]
    stat = info["stat"]
    content_lines = [
        "commit {}: {}".format(short_sha, subject),
    ]
    body = info["body"].strip()
    if body:
        content_lines.append("")
        content_lines.append(body)
    if stat:
        content_lines.append("")
        content_lines.append(stat)
    content = "\n".join(content_lines).strip()

    metadata: Dict[str, Any] = {
        "sha": info["sha"],
        "short_sha": short_sha,
        "subject": subject,
        "author": info["author"],
        "files_changed": info["files"],
        "file_count": len(info["files"]),
        "repo_root": info["repo_root"],
    }
    if info["branch"]:
        metadata["branch"] = info["branch"]

    proj_override = ProjectContext(
        project_id=Path(info["repo_root"]).name,
        repo_root=Path(info["repo_root"]),
        branch=info["branch"],
        last_commit_subject=subject,
        cwd=repo_path,
    )
    return _push(
        event_type=EVENT_COMMIT,
        content=content,
        metadata=metadata,
        config=cfg,
        project=proj_override,
    )


def push_test_pass(
    suite_name: str,
    duration: float,
    test_count: int,
    runner: str,
    config: Optional[BridgeConfig] = None,
    project: Optional[ProjectContext] = None,
) -> PushOutcome:
    """Push a green-suite event.

    Called by the pytest plugin on session finish (exitstatus=0) and
    by shell wrappers around ``npm test`` / ``cargo test`` / ``go test``
    that users paste into their shell rc. A passing test run is a
    strong signal that the current code state is worth remembering.
    """
    suite = (suite_name or "").strip() or "unknown"
    runner_clean = (runner or "").strip() or "unknown"
    try:
        duration_f = float(duration)
    except (TypeError, ValueError):
        duration_f = 0.0
    try:
        count_i = int(test_count)
    except (TypeError, ValueError):
        count_i = 0

    content = "{} passed: {} tests in {:.2f}s ({})".format(
        suite, count_i, duration_f, runner_clean
    )
    metadata: Dict[str, Any] = {
        "suite": suite,
        "duration_seconds": duration_f,
        "test_count": count_i,
        "runner": runner_clean,
    }
    return _push(
        event_type=EVENT_TEST_PASS,
        content=content,
        metadata=metadata,
        config=config,
        project=project,
    )
