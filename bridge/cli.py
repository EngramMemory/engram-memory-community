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
from .install import install_claude_code_hook, install_git_hooks
from .project import detect_project
from .pull import PullOutcome, run_pull
from .push import (
    EVENT_COMMIT,
    EVENT_MANUAL,
    EVENT_TEST_PASS,
    PushOutcome,
    push_git_commit,
    push_manual,
    push_test_pass,
)


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
    pull.add_argument(
        "--scope",
        dest="scope",
        default=None,
        help=(
            "Search scope: 'personal' (default) or 'hive:<hive_id>' "
            "to pull from a shared hive collection."
        ),
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
    install.add_argument(
        "--git-hooks",
        dest="git_hooks",
        action="store_true",
        help=(
            "Install a post-commit hook that pushes each commit to "
            "the Engram cloud. Idempotent; merges into any existing "
            "hook and creates a timestamped backup."
        ),
    )
    install.add_argument(
        "--repo",
        dest="repo",
        default=None,
        help=(
            "Repo directory for --git-hooks. Defaults to the current "
            "working directory."
        ),
    )

    push = sub.add_parser(
        "push",
        help="Push a manual milestone memory to the Engram cloud.",
    )
    push.add_argument(
        "message",
        help="Free-form text to store (e.g. 'shipped wave 2').",
    )
    push.add_argument(
        "--type",
        dest="push_type",
        default=EVENT_MANUAL,
        help="Event type label. Default: milestone.",
    )
    push.add_argument(
        "--metadata",
        dest="metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Extra metadata as key=value pairs. Repeat for multiple "
            "entries. Values are stored as strings."
        ),
    )
    push.add_argument(
        "--hive",
        dest="hive",
        action="append",
        default=[],
        metavar="HIVE_ID",
        help=(
            "Also share this memory with a hive. Pass --hive more "
            "than once to fan out to several hives. The caller must "
            "already be a member of each listed hive."
        ),
    )

    hive = sub.add_parser(
        "hive",
        help="Manage hive scopes (list/create/add-member).",
    )
    hive_sub = hive.add_subparsers(dest="hive_command")

    hive_sub.add_parser(
        "list",
        help="List hives the current api_key belongs to.",
    )

    hive_create = hive_sub.add_parser(
        "create",
        help="Create a new hive and become its owner.",
    )
    hive_create.add_argument("name", help="Hive display name.")
    hive_create.add_argument(
        "--slug",
        dest="slug",
        required=True,
        help="URL slug (lowercase, 3-48 chars, hyphens allowed).",
    )

    hive_add = hive_sub.add_parser(
        "add-member",
        help="Add a user to a hive. Caller must be owner or admin.",
    )
    hive_add.add_argument("hive_id", help="Target hive_id (uuid).")
    hive_add.add_argument("user_id", help="Target user_id (uuid).")
    hive_add.add_argument(
        "--role",
        dest="role",
        default="member",
        choices=["member", "admin"],
        help="Role to assign. Default: member.",
    )

    push_commit = sub.add_parser(
        "push-commit",
        help=(
            "Push the current HEAD commit. Wired from the post-commit "
            "git hook."
        ),
    )
    push_commit.add_argument(
        "--repo",
        dest="repo",
        default=None,
        help="Repo directory. Defaults to the current working directory.",
    )

    push_test = sub.add_parser(
        "push-test",
        help="Push a green test-suite event.",
    )
    push_test.add_argument("suite", help="Suite name.")
    push_test.add_argument(
        "duration", type=float, help="Wall time in seconds."
    )
    push_test.add_argument("count", type=int, help="Test count.")
    push_test.add_argument(
        "--runner",
        dest="runner",
        default="pytest",
        choices=["pytest", "jest", "cargo", "go", "custom"],
        help="Test runner. Default: pytest.",
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
            scope=getattr(args, "scope", None),
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
    if args.git_hooks:
        repo = args.repo or str(Path.cwd())
        try:
            outcome = install_git_hooks(repo)
        except Exception as exc:  # noqa: BLE001
            sys.stdout.write(
                "git-hooks install failed: {}\n".format(exc)
            )
        else:
            sys.stdout.write(outcome.message + "\n")
        did_anything = True
    if not did_anything:
        sys.stdout.write(
            "Nothing to install. Pass --claude-code, --git-hooks, "
            "and/or --write-config-template.\n"
        )
    return 0


def _parse_metadata_pairs(pairs: List[str]) -> dict:
    """Parse ``--metadata k=v`` pairs into a dict. Silently drops
    malformed entries rather than failing the push."""
    out: dict = {}
    for raw in pairs or []:
        if not isinstance(raw, str) or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        if not key:
            continue
        out[key] = value.strip()
    return out


def _cmd_push(args: argparse.Namespace) -> int:
    try:
        outcome: PushOutcome = push_manual(
            message=args.message,
            push_type=args.push_type,
            metadata=_parse_metadata_pairs(args.metadata),
            share_with=_hive_scopes(getattr(args, "hive", None)),
        )
    except Exception:  # noqa: BLE001
        return 0
    _emit_push_status(outcome)
    return 0


def _hive_scopes(hives: Optional[List[str]]) -> List[str]:
    """Convert a list of bare hive ids from ``--hive`` into scope strings.

    Users can type either ``abc-123`` or ``hive:abc-123`` — both
    should work, so we strip an optional leading prefix and add our
    own. Duplicates collapse. Empty / whitespace entries drop.
    """
    if not hives:
        return []
    seen: List[str] = []
    for raw in hives:
        if not isinstance(raw, str):
            continue
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("hive:"):
            stripped = stripped[len("hive:"):]
        if not stripped:
            continue
        scope = "hive:{}".format(stripped)
        if scope not in seen:
            seen.append(scope)
    return seen


def _cmd_push_commit(args: argparse.Namespace) -> int:
    try:
        repo = args.repo or str(Path.cwd())
        outcome: PushOutcome = push_git_commit(repo)
    except Exception:  # noqa: BLE001
        return 0
    _emit_push_status(outcome)
    return 0


def _cmd_push_test(args: argparse.Namespace) -> int:
    try:
        outcome: PushOutcome = push_test_pass(
            suite_name=args.suite,
            duration=args.duration,
            test_count=args.count,
            runner=args.runner,
        )
    except Exception:  # noqa: BLE001
        return 0
    _emit_push_status(outcome)
    return 0


def _cmd_hive(args: argparse.Namespace) -> int:
    """Dispatch ``engram-bridge hive <sub>``. Every branch honors the
    disabled chain — silent exit 0 when the bridge is off."""
    sub = getattr(args, "hive_command", None)
    if sub == "list":
        return _cmd_hive_list()
    if sub == "create":
        return _cmd_hive_create(args)
    if sub == "add-member":
        return _cmd_hive_add_member(args)
    # Bare `engram-bridge hive` — print a short usage hint.
    sys.stdout.write(
        "hive commands: list | create <name> --slug <slug> | "
        "add-member <hive_id> <user_id> [--role member|admin]\n"
    )
    return 0


def _cmd_hive_list() -> int:
    cfg = load_config()
    if not cfg.enabled:
        return 0
    try:
        client = EngramClient(cfg)
        hives = client.list_hives()
    except Exception:  # noqa: BLE001
        return 0
    if hives is None:
        sys.stdout.write("hives: api error\n")
        return 0
    if not hives:
        sys.stdout.write("hives: (none)\n")
        return 0
    for t in hives:
        if not isinstance(t, dict):
            continue
        hive_id = str(t.get("id", ""))
        name = str(t.get("name", ""))
        slug = str(t.get("slug", ""))
        role = str(t.get("role", ""))
        member_count = t.get("member_count", "?")
        sys.stdout.write(
            "{}  {}  ({})  role={}  members={}\n".format(
                hive_id, name, slug, role, member_count
            )
        )
    return 0


def _cmd_hive_create(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not cfg.enabled:
        return 0
    name = (args.name or "").strip()
    slug = (args.slug or "").strip().lower()
    if not name or not slug:
        sys.stdout.write("hive create: name and --slug are required\n")
        return 0
    try:
        client = EngramClient(cfg)
        hive = client.create_hive(name=name, slug=slug)
    except Exception:  # noqa: BLE001
        return 0
    if hive is None:
        sys.stdout.write("hive create: api error (slug may be taken)\n")
        return 0
    hive_id = str(hive.get("id", ""))
    sys.stdout.write("hive created {} ({})\n".format(hive_id, slug))
    return 0


def _cmd_hive_add_member(args: argparse.Namespace) -> int:
    cfg = load_config()
    if not cfg.enabled:
        return 0
    hive_id = (args.hive_id or "").strip()
    user_id = (args.user_id or "").strip()
    role = (args.role or "member").strip().lower()
    if not hive_id or not user_id:
        sys.stdout.write("hive add-member: hive_id and user_id are required\n")
        return 0
    try:
        client = EngramClient(cfg)
        result = client.add_hive_member(hive_id=hive_id, user_id=user_id, role=role)
    except Exception:  # noqa: BLE001
        return 0
    if result is None:
        sys.stdout.write("hive add-member: api error\n")
        return 0
    sys.stdout.write(
        "hive add-member ok hive={} user={} role={}\n".format(hive_id, user_id, role)
    )
    return 0


def _emit_push_status(outcome: PushOutcome) -> None:
    """Write one short status line to stdout for interactive feedback.

    Stays quiet when the bridge is disabled so the CLI honors the
    'never break a workflow' rule — users who install a git hook
    before configuring a key should see nothing at all.
    """
    if outcome.status == "disabled":
        return
    if outcome.status == "sent":
        suffix = ""
        if outcome.memory_id:
            suffix = " ({})".format(outcome.memory_id)
        sys.stdout.write(
            "pushed {}{}\n".format(outcome.event_type, suffix)
        )
        return
    if outcome.status == "skipped":
        sys.stdout.write(
            "skipped {}: {}\n".format(outcome.event_type, outcome.reason)
        )
        return
    if outcome.status == "failed":
        sys.stdout.write(
            "push {} failed: {}\n".format(
                outcome.event_type, outcome.reason
            )
        )


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
    if ns.command == "push":
        return _cmd_push(ns)
    if ns.command == "push-commit":
        return _cmd_push_commit(ns)
    if ns.command == "push-test":
        return _cmd_push_test(ns)
    if ns.command == "hive":
        return _cmd_hive(ns)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
