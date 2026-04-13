"""argparse entry point for the `engram bridge` CLI.

Exposes four subcommands: ``pull``, ``status``, ``install``, and a
bare ``engram bridge`` that prints help.

Hard rule: every command must exit 0 when the bridge is disabled or
failing. A disabled bridge never breaks a user's workflow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import (
    CONFIG_PATH,
    BridgeConfig,
    load_config,
    write_config_template,
)
from .client import EngramClient
from .install import install_claude_code_hook
from .project import detect_project
from .pull import PullOutcome, run_pull


PROG = "engram bridge"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Engram Bridge — pulls relevant memories from the Engram "
            "cloud and injects them into agent sessions. Disabled "
            "unless ~/.engram/config.yaml is configured with a valid "
            "api_key."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    pull = sub.add_parser(
        "pull",
        help="Pull context for the current working directory.",
    )
    pull.add_argument(
        "--project",
        dest="project",
        default=None,
        help="Override the detected project_id.",
    )
    pull.add_argument(
        "--top-k",
        dest="top_k",
        type=int,
        default=None,
        help="Override the configured top_k.",
    )

    status = sub.add_parser(
        "status",
        help="Print config path, enabled state, project mapping, API health.",
    )
    status.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )

    install = sub.add_parser(
        "install",
        help="Install shell integrations.",
    )
    install.add_argument(
        "--claude-code",
        dest="claude_code",
        action="store_true",
        help="Register a SessionStart hook in ~/.claude/settings.json.",
    )
    install.add_argument(
        "--write-config-template",
        dest="write_template",
        action="store_true",
        help=(
            "Create ~/.engram/config.yaml from the template if it "
            "doesn't exist."
        ),
    )

    return parser


# ----------------------------------------------------------------------
# Command handlers. Each returns an int exit code. All must return 0 on
# a disabled or failing bridge.
# ----------------------------------------------------------------------


def _cmd_pull(args: argparse.Namespace) -> int:
    try:
        outcome: PullOutcome = run_pull(
            project_override=args.project,
            top_k_override=args.top_k,
        )
    except Exception:  # noqa: BLE001 — belt-and-suspenders silence
        return 0
    if outcome.output:
        sys.stdout.write(outcome.output)
        if not outcome.output.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    project = detect_project()

    if args.as_json:
        return _status_json(cfg, project)

    lines: List[str] = []
    lines.append("engram bridge status")
    lines.append("-" * 40)
    lines.append("config path: {}".format(cfg.config_path))
    lines.append("enabled:     {}".format("yes" if cfg.enabled else "no"))
    if not cfg.enabled:
        lines.append("reason:      {}".format(cfg.reason))
    lines.append("cwd:         {}".format(project.cwd))
    lines.append("project_id:  {}".format(project.project_id))
    if project.repo_root:
        lines.append("repo_root:   {}".format(project.repo_root))
    if project.branch:
        lines.append("branch:      {}".format(project.branch))
    if project.last_commit_subject:
        lines.append("last commit: {}".format(project.last_commit_subject))
    lines.append("query:       {}".format(project.build_query()))

    if cfg.enabled:
        lines.append("api_base:    {}".format(cfg.api_base))
        lines.append("top_k:       {}".format(cfg.top_k_for(project.project_id)))
        client = EngramClient(cfg)
        healthy = client.health()
        lines.append(
            "api health:  {}".format("ok" if healthy else "unreachable")
        )

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _status_json(cfg: BridgeConfig, project) -> int:
    import json as _json

    payload = {
        "config_path": str(cfg.config_path),
        "enabled": cfg.enabled,
        "reason": cfg.reason,
        "cwd": str(project.cwd),
        "project_id": project.project_id,
        "repo_root": str(project.repo_root) if project.repo_root else None,
        "branch": project.branch,
        "last_commit_subject": project.last_commit_subject,
        "query": project.build_query(),
    }
    if cfg.enabled:
        payload["api_base"] = cfg.api_base
        payload["top_k"] = cfg.top_k_for(project.project_id)
        payload["api_health"] = EngramClient(cfg).health()
    sys.stdout.write(_json.dumps(payload, indent=2) + "\n")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    did_anything = False
    if args.write_template:
        path = write_config_template()
        sys.stdout.write(
            "config template: {} ({})\n".format(
                path, "exists" if path.exists() else "created"
            )
        )
        did_anything = True
    if args.claude_code:
        result = install_claude_code_hook()
        sys.stdout.write(result.message + "\n")
        did_anything = True
    if not did_anything:
        sys.stdout.write(
            "Nothing to install. Pass --claude-code and/or "
            "--write-config-template.\n"
        )
    return 0


# ----------------------------------------------------------------------
# Top-level entry. Supports being called as `engram bridge <cmd>` via an
# `engram` wrapper script OR directly as `engram-bridge <cmd>`.
# ----------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    # The `engram` wrapper strips "bridge" before delegating, but when
    # users run it directly the first arg may still be "bridge" — accept
    # both forms for convenience.
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "bridge":
        args_list = args_list[1:]

    parser = _build_parser()

    if not args_list:
        parser.print_help()
        return 0

    try:
        ns = parser.parse_args(args_list)
    except SystemExit as exc:
        # argparse exits 2 on parse errors; preserve that for real
        # CLI misuse but let --help (code 0) pass through.
        return int(exc.code or 0)

    if ns.command == "pull":
        return _cmd_pull(ns)
    if ns.command == "status":
        return _cmd_status(ns)
    if ns.command == "install":
        return _cmd_install(ns)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
