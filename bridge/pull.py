"""The main `engram bridge pull` command.

Returns a markdown preamble suitable for injection at agent session
start. Silent on every kind of failure — the caller gets either useful
context or an empty string, never an error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional

import httpx

from .client import EngramClient, SearchResult
from .config import BridgeConfig, load_config, log_path
from .project import ProjectContext, detect_project


_LOGGER_NAME = "engram.bridge"
_logger_configured = False


def _get_logger() -> logging.Logger:
    """Lazy logger that writes to ``~/.engram/bridge.log`` and nowhere
    else. Stdout/stderr stay clean so a disabled or failing bridge can
    never leak into an agent's session."""
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
class PullOutcome:
    """Result of a pull. ``output`` is always safe to print to stdout —
    it's either a useful markdown block or an empty string."""

    output: str
    used: bool  # True iff results were returned and rendered
    reason: str  # Human-readable explanation for `status`
    project_id: str
    query: str
    result_count: int


def _format_results(
    project_id: str, results: List[SearchResult]
) -> str:
    lines: List[str] = [
        "# Engram context for {}".format(project_id),
        "",
    ]
    for r in results:
        content = (r.content or "").strip()
        if not content:
            continue
        score = "{:.2f}".format(r.score)
        lines.append("{} (score: {})".format(content, score))
    lines.append("")
    return "\n".join(lines)


def _normalize_scope(raw: Optional[str]) -> str:
    """Normalize a caller-supplied scope string.

    Accepts ``None`` / ``"personal"`` (default) or ``"team:<id>"``. An
    invalid string collapses to ``"personal"`` rather than raising —
    the bridge never breaks a workflow, so bad input falls back to
    the safe default.
    """
    if not raw:
        return "personal"
    value = raw.strip()
    if not value or value == "personal":
        return "personal"
    if value.startswith("team:") and len(value) > len("team:"):
        return value
    return "personal"


def run_pull(
    project_override: Optional[str] = None,
    top_k_override: Optional[int] = None,
    config: Optional[BridgeConfig] = None,
    project: Optional[ProjectContext] = None,
    scope: Optional[str] = None,
) -> PullOutcome:
    """Execute the pull and return a ``PullOutcome``.

    Never raises. Never writes to stdout. Callers (the CLI) decide what
    to do with ``outcome.output``. ``scope`` forwards Wave 3's
    ``scope`` param to ``/v1/search``; invalid values collapse to
    ``"personal"``.
    """
    logger = _get_logger()
    cfg = config or load_config()
    proj = project or detect_project()

    if not cfg.enabled:
        logger.info("pull skipped: %s", cfg.reason)
        return PullOutcome(
            output="",
            used=False,
            reason="disabled: {}".format(cfg.reason),
            project_id=proj.project_id,
            query="",
            result_count=0,
        )

    project_id = project_override or proj.project_id
    top_k = top_k_override or cfg.top_k_for(project_id)
    query = proj.build_query()
    if project_override and project_override not in query:
        query = "{}: {}".format(project_override, query)
    effective_scope = _normalize_scope(scope)

    client = EngramClient(cfg)

    if not client.health():
        logger.warning(
            "pull skipped: API health check failed for %s", cfg.api_base
        )
        return PullOutcome(
            output="",
            used=False,
            reason="API unreachable at {}".format(cfg.api_base),
            project_id=project_id,
            query=query,
            result_count=0,
        )

    try:
        results = client.search_raw(
            query=query, top_k=top_k, scope=effective_scope
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "pull failed: HTTP %s from %s",
            exc.response.status_code,
            cfg.api_base,
        )
        return PullOutcome(
            output="",
            used=False,
            reason="search HTTP {}".format(exc.response.status_code),
            project_id=project_id,
            query=query,
            result_count=0,
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.warning("pull failed: %s", exc)
        return PullOutcome(
            output="",
            used=False,
            reason="search error: {}".format(exc),
            project_id=project_id,
            query=query,
            result_count=0,
        )

    if not results:
        logger.info(
            "pull: 0 results for project=%s query=%r", project_id, query
        )
        return PullOutcome(
            output="",
            used=False,
            reason="no results",
            project_id=project_id,
            query=query,
            result_count=0,
        )

    output = _format_results(project_id, results)
    logger.info(
        "pull: %d results for project=%s", len(results), project_id
    )
    return PullOutcome(
        output=output,
        used=True,
        reason="ok",
        project_id=project_id,
        query=query,
        result_count=len(results),
    )
