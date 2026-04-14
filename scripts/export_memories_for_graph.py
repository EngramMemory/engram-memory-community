#!/usr/bin/env python3
"""Export Engram memories to a folder of Markdown files for graphify.

Each memory becomes one <id>.md file with YAML frontmatter and the memory
text as the body. Also writes `_edges.json` preserving the real Kuzu graph
edges (co-retrieval, entity mentions, related-to) alongside the docs.

Usage:
    python scripts/export_memories_for_graph.py --output /tmp/engram-graph-input
    python scripts/export_memories_for_graph.py --output /tmp/out --user alice

The `--user` flag is accepted for forward compatibility but the Community
Edition graph layer does not currently partition memories by user, so it
is only used as an informational tag in the emitted frontmatter.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `src/recall` importable whether run from repo root or elsewhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "recall"))

from graph_layer import EngramGraphLayer  # noqa: E402


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(memory_id: str) -> str:
    cleaned = _SAFE_NAME.sub("_", memory_id).strip("_")
    return cleaned or "memory"


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_markdown(mem: dict, user: str | None) -> str:
    created_iso = datetime.fromtimestamp(
        mem.get("created_at") or 0.0, tz=timezone.utc
    ).isoformat()
    entity_names = [e["name"] for e in mem.get("entities", []) if e.get("name")]

    lines = ["---", f'id: "{yaml_escape(mem["id"])}"', f"created_at: {created_iso}"]
    if mem.get("category"):
        lines.append(f'category: "{yaml_escape(mem["category"])}"')
    if user:
        lines.append(f'user: "{yaml_escape(user)}"')
    if entity_names:
        lines.append("entities:")
        for name in entity_names:
            lines.append(f'  - "{yaml_escape(name)}"')
    else:
        lines.append("entities: []")
    lines.append("tags: []")
    lines.append("---")
    lines.append("")
    lines.append(mem.get("content") or "")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--output", required=True, help="Directory to write .md files into"
    )
    parser.add_argument(
        "--user",
        default=None,
        help="Optional user id (tag only; community graph is single-tenant)",
    )
    parser.add_argument(
        "--graph-db",
        default=None,
        help="Path to the Kuzu graph dir (defaults to $ENGRAM_DATA_DIR/graph.kuzu "
        "or .engram/graph.kuzu relative to repo root)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.graph_db:
        db_path = Path(args.graph_db).expanduser().resolve()
    else:
        data_dir = os.environ.get("ENGRAM_DATA_DIR") or str(REPO_ROOT / ".engram")
        db_path = Path(data_dir) / "graph.kuzu"

    if not db_path.exists():
        print(
            f"[export] No graph database at {db_path}. "
            f"Store some memories first, then re-run.",
            file=sys.stderr,
        )
        return 0

    graph = EngramGraphLayer(str(db_path))
    graph.ensure_schema()

    memories = graph.export_all_memories()
    edges = graph.export_all_edges()
    graph.close()

    if not memories:
        print("[export] Graph is empty — no memories to export.")
        (out_dir / "_edges.json").write_text(json.dumps(edges, indent=2))
        return 0

    used_names: set[str] = set()
    written = 0
    for mem in memories:
        base = safe_filename(mem["id"])
        name = f"{base}.md"
        i = 1
        while name in used_names:
            i += 1
            name = f"{base}_{i}.md"
        used_names.add(name)
        (out_dir / name).write_text(render_markdown(mem, args.user))
        written += 1

    (out_dir / "_edges.json").write_text(json.dumps(edges, indent=2))

    print(
        f"[export] Wrote {written} memory file(s) and _edges.json to {out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
