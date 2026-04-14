#!/usr/bin/env python3
"""Export Engram memories to a folder of Markdown files for graphify.

Pulls real memories from the running engram-memory container rather than
the repo's local scratch database. Data flow:

1. Memories + payloads come from Qdrant's REST `scroll` API on the live
   collection (default: ``agent-memory`` at ``http://localhost:6333``).
2. Graph edges come from ``docker exec engram-memory`` running a tiny
   Kuzu query against ``/data/engram/graph.kuzu`` inside the container.
   If docker exec fails or Kuzu has no edges, ``_edges.json`` is written
   as ``[]`` and a warning is logged — export does not crash.

Each memory point becomes one ``<id>.md`` file with YAML frontmatter and
the memory content as the body. Fields that are absent from the payload
are simply omitted — nothing is fabricated.

Usage:
    python scripts/export_memories_for_graph.py --output /tmp/engram-graph-input
    python scripts/export_memories_for_graph.py --output /tmp/out --limit 500

Only stdlib is used (urllib, json, subprocess) — no new dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_FRONTMATTER_KEYS_SKIP = {"content", "text", "memory", "body"}


def safe_filename(memory_id: str) -> str:
    cleaned = _SAFE_NAME.sub("_", str(memory_id)).strip("_")
    return cleaned or "memory"


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _post_json(url: str, body: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def scroll_qdrant(
    qdrant_url: str, collection: str, limit: int
) -> list[dict[str, Any]]:
    """Page through every point in the collection using Qdrant scroll."""
    url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll"
    points: list[dict[str, Any]] = []
    offset: Any = None
    page_size = min(256, max(1, limit))
    while len(points) < limit:
        body: dict[str, Any] = {
            "limit": page_size,
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            body["offset"] = offset
        try:
            resp = _post_json(url, body)
        except urllib.error.HTTPError as e:
            raise SystemExit(
                f"[export] Qdrant scroll failed: HTTP {e.code} — {e.read().decode('utf-8', 'replace')[:300]}"
            )
        except urllib.error.URLError as e:
            raise SystemExit(
                f"[export] Could not reach Qdrant at {qdrant_url}: {e.reason}"
            )
        result = resp.get("result") or {}
        batch = result.get("points") or []
        points.extend(batch)
        next_offset = result.get("next_page_offset")
        if not batch or next_offset is None:
            break
        offset = next_offset
    return points[:limit]


def _payload_content(payload: dict[str, Any]) -> str:
    for key in ("content", "text", "memory", "body"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # Fall back to a deterministic dump if no obvious content field exists.
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _render_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{yaml_escape(value)}"'
    return None


def _render_list(values: Iterable[Any]) -> list[str] | None:
    items: list[str] = []
    for v in values:
        rendered = _render_scalar(v)
        if rendered is None:
            return None
        items.append(rendered)
    return items


def render_markdown(point: dict[str, Any]) -> str:
    payload = point.get("payload") or {}
    mem_id = str(point.get("id", ""))
    content = _payload_content(payload)

    lines: list[str] = ["---", f'id: "{yaml_escape(mem_id)}"']

    for key, value in payload.items():
        if key in _FRONTMATTER_KEYS_SKIP:
            continue
        scalar = _render_scalar(value)
        if scalar is not None:
            lines.append(f"{key}: {scalar}")
            continue
        if isinstance(value, list):
            rendered_list = _render_list(value)
            if rendered_list is None:
                continue
            if not rendered_list:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in rendered_list:
                    lines.append(f"  - {item}")

    lines.append("---")
    lines.append("")
    lines.append(content)
    lines.append("")
    return "\n".join(lines)


_KUZU_DUMP_SNIPPET = r"""
import json, sys
try:
    import kuzu
except Exception as e:
    print(json.dumps({"__error__": f"kuzu import failed: {e}"}))
    sys.exit(0)

edges = []
try:
    db = kuzu.Database("/data/engram/graph.kuzu", read_only=True)
    conn = kuzu.Connection(db)
    # Discover rel tables and dump every edge we can find.
    try:
        rel_rows = conn.execute("CALL show_tables() RETURN *;")
        rel_tables = []
        while rel_rows.has_next():
            row = rel_rows.get_next()
            # row order: id, name, type, ...
            name = row[1] if len(row) > 1 else None
            ttype = row[2] if len(row) > 2 else None
            if name and ttype and str(ttype).upper().startswith("REL"):
                rel_tables.append(str(name))
    except Exception as e:
        rel_tables = []
    for table in rel_tables:
        try:
            q = f"MATCH (a)-[r:{table}]->(b) RETURN a, b, r LIMIT 100000;"
            res = conn.execute(q)
            while res.has_next():
                row = res.get_next()
                a, b, r = row[0], row[1], row[2]
                def _id(node):
                    if isinstance(node, dict):
                        for k in ("id", "_id", "name"):
                            if k in node:
                                return node[k]
                        return json.dumps(node, default=str, sort_keys=True)
                    return str(node)
                edge = {"type": table, "source": _id(a), "target": _id(b)}
                if isinstance(r, dict):
                    for k in ("weight", "count", "score"):
                        if k in r:
                            edge[k] = r[k]
                edges.append(edge)
        except Exception:
            continue
except Exception as e:
    print(json.dumps({"__error__": f"kuzu query failed: {e}"}))
    sys.exit(0)

print(json.dumps(edges))
"""


def dump_edges_via_docker(container: str) -> tuple[list[dict[str, Any]], str | None]:
    """Return (edges, warning). warning is None on success."""
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", container, "python", "-c", _KUZU_DUMP_SNIPPET],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return [], "docker CLI not found on host — skipping edge export"
    except subprocess.TimeoutExpired:
        return [], "docker exec for edge dump timed out — skipping edges"
    if proc.returncode != 0:
        return [], f"docker exec failed (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
    out = proc.stdout.strip()
    if not out:
        return [], "docker exec produced no output for edge dump"
    try:
        parsed = json.loads(out.splitlines()[-1])
    except json.JSONDecodeError as e:
        return [], f"edge dump returned non-JSON: {e}"
    if isinstance(parsed, dict) and "__error__" in parsed:
        return [], f"kuzu edge dump error: {parsed['__error__']}"
    if not isinstance(parsed, list):
        return [], "edge dump returned unexpected shape"
    return parsed, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--output", required=True, help="Directory to write .md files into")
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Base URL of the Qdrant REST API",
    )
    parser.add_argument(
        "--collection",
        default="agent-memory",
        help="Qdrant collection name to scroll",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum number of memories to export",
    )
    parser.add_argument(
        "--container",
        default="engram-memory",
        help="Name of the engram Docker container (for edge dump)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    points = scroll_qdrant(args.qdrant_url, args.collection, args.limit)

    if not points:
        (out_dir / "_edges.json").write_text("[]\n")
        print(
            f"[export] Collection '{args.collection}' at {args.qdrant_url} is empty — "
            f"no memories to export."
        )
        return 0

    used_names: set[str] = set()
    written = 0
    for point in points:
        base = safe_filename(point.get("id", "memory"))
        name = f"{base}.md"
        i = 1
        while name in used_names:
            i += 1
            name = f"{base}_{i}.md"
        used_names.add(name)
        (out_dir / name).write_text(render_markdown(point))
        written += 1

    edges, edge_warning = dump_edges_via_docker(args.container)
    if edge_warning:
        print(f"[export] warning: {edge_warning}", file=sys.stderr)
    (out_dir / "_edges.json").write_text(json.dumps(edges, indent=2) + "\n")

    print(f"[export] wrote {written} memories, {len(edges)} edges to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
