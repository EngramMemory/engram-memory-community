"""Map a working directory to a project_id and build a pull query.

The mapping is intentionally simple for Wave 1:

- If cwd is inside a git repo, project_id = basename of the repo root.
- Otherwise, project_id = basename of cwd.

The query combines repo name + branch + last commit subject so that the
cloud API can return context relevant to the current focus of work.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProjectContext:
    """Everything we need to build a pull query for a given directory."""

    project_id: str
    repo_root: Optional[Path]
    branch: Optional[str]
    last_commit_subject: Optional[str]
    cwd: Path

    @property
    def is_git_repo(self) -> bool:
        return self.repo_root is not None

    def build_query(self) -> str:
        """Compose the query string for `/v1/search`.

        Format: ``"<project_id> <branch>: <last commit subject>"``
        with graceful fallback when any piece is missing.
        """
        parts: list[str] = [self.project_id]
        if self.branch:
            parts.append(self.branch)
        head = " ".join(parts).strip()
        if self.last_commit_subject:
            return "{}: {}".format(head, self.last_commit_subject)
        return head


def _run_git(args: list[str], cwd: Path, timeout: float = 1.5) -> Optional[str]:
    """Run a git command, return stripped stdout or None on any failure."""
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
    out = (result.stdout or "").strip()
    return out or None


def detect_project(cwd: Optional[Path] = None) -> ProjectContext:
    """Detect project context for the given cwd (default: real cwd)."""
    here = (cwd or Path.cwd()).resolve()

    toplevel = _run_git(["rev-parse", "--show-toplevel"], here)
    repo_root = Path(toplevel) if toplevel else None

    if repo_root is not None:
        project_id = repo_root.name
        branch = _run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], repo_root
        )
        if branch == "HEAD":
            branch = None
        last_subject = _run_git(
            ["log", "-1", "--pretty=%s"], repo_root
        )
    else:
        project_id = here.name
        branch = None
        last_subject = None

    return ProjectContext(
        project_id=project_id,
        repo_root=repo_root,
        branch=branch,
        last_commit_subject=last_subject,
        cwd=here,
    )
