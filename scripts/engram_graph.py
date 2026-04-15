#!/usr/bin/env python3
"""Drive the vendored graphify library on a dump of engram memories.

Flow:
1. Call ``scripts/export_memories_for_graph.py`` to pull every memory from
   the running engram container's Qdrant collection. That produces one
   ``<id>.md`` per memory plus ``_edges.json`` in a temp directory.
2. Translate those markdown files + edges into a graphify extraction dict
   (``{"nodes": [...], "edges": [...]}``). One node per memory.
3. Call the vendored ``graphify.build.build_from_json`` → ``cluster`` →
   ``to_html`` / ``to_json`` pipeline to render ``graphify-out/graph.html``
   and ``graphify-out/graph.json`` under the requested output directory.

We deliberately skip ``graphify.extract`` (tree-sitter code parsing) —
memories are free-form prose, not source code, so we assemble the
extraction dict ourselves. Everything downstream is the real vendored
graphify code.

Usage:
    python3 scripts/engram_graph.py --output /tmp/engram-graph-run
    python3 scripts/engram_graph.py --output ~/engram-graph --limit 500

Exit codes:
    0  success — ``graph.html`` was written
    1  exporter failure
    2  graphify build failure
    3  empty collection (nothing to graph)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = REPO_ROOT / "vendor" / "graphify"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

# Imported after sys.path injection so the vendored copy wins.
from graphify.build import build_from_json  # noqa: E402
from graphify.cluster import cluster  # noqa: E402
from graphify.export import to_html, to_json  # noqa: E402


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_SCALAR_RE = re.compile(r'^([A-Za-z0-9_]+):\s*"?(.*?)"?\s*$')


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter, body) for one exported memory file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    front_raw, body = m.group(1), m.group(2)
    front: dict[str, Any] = {}
    for line in front_raw.splitlines():
        sm = _SCALAR_RE.match(line.strip())
        if sm:
            front[sm.group(1)] = sm.group(2)
    return front, body.strip()


def summarise(body: str, limit: int = 80) -> str:
    """Short label for a memory node — first line, truncated."""
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if len(first) <= limit:
        return first or "(empty memory)"
    return first[: limit - 1].rstrip() + "\u2026"


def run_exporter(
    output_dir: Path,
    limit: int,
    qdrant_url: str,
    collection: str,
    container: str,
    min_similarity: float,
    neighbors_per_node: int,
) -> None:
    script = REPO_ROOT / "scripts" / "export_memories_for_graph.py"
    cmd = [
        sys.executable,
        str(script),
        "--output",
        str(output_dir),
        "--qdrant-url",
        qdrant_url,
        "--collection",
        collection,
        "--limit",
        str(limit),
        "--container",
        container,
        "--min-similarity",
        str(min_similarity),
        "--neighbors-per-node",
        str(neighbors_per_node),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(1)


def build_extraction(input_dir: Path) -> dict[str, Any]:
    """Turn a folder of exported memories into a graphify extraction dict."""
    md_files = sorted(p for p in input_dir.glob("*.md") if not p.name.startswith("_"))
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for md in md_files:
        front, body = parse_markdown(md)
        mem_id = front.get("id") or md.stem
        node = {
            "id": mem_id,
            "label": summarise(body) if body else summarise(front.get("id", mem_id)),
            "file_type": "rationale",
            "source_file": md.name,
        }
        # Pass through handful of payload fields that are useful in the UI.
        for k in ("created_at", "user_id", "tier", "importance"):
            if k in front:
                node[k] = front[k]
        nodes.append(node)
        node_ids.add(mem_id)

    edges: list[dict[str, Any]] = []
    edges_file = input_dir / "_edges.json"
    if edges_file.exists():
        try:
            raw_edges = json.loads(edges_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw_edges = []
        for e in raw_edges:
            src = str(e.get("source", ""))
            tgt = str(e.get("target", ""))
            if src in node_ids and tgt in node_ids:
                edge_dict: dict[str, Any] = {
                    "source": src,
                    "target": tgt,
                    "relation": str(e.get("type", "related")),
                    "confidence": "EXTRACTED",
                    "source_file": "_edges.json",
                }
                if "weight" in e:
                    try:
                        edge_dict["weight"] = float(e["weight"])
                    except (TypeError, ValueError):
                        pass
                edges.append(edge_dict)

    return {"nodes": nodes, "edges": edges}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--output", required=True, help="Directory where graphify-out/ will be written")
    ap.add_argument("--limit", type=int, default=10000, help="Maximum number of memories to export")
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--collection", default="agent-memory")
    ap.add_argument("--container", default="engram-memory")
    ap.add_argument("--min-similarity", type=float, default=0.5,
                    help="Minimum cosine similarity for similarity edges")
    ap.add_argument("--neighbors-per-node", type=int, default=5,
                    help="Max nearest neighbors queried per memory")
    ap.add_argument("--keep-input", action="store_true", help="Keep the exported markdown dir under <output>/input/")
    args = ap.parse_args()

    out_root = Path(args.output).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    input_dir = out_root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    graphify_out = out_root / "graphify-out"
    graphify_out.mkdir(parents=True, exist_ok=True)

    print(f"[engram-graph] exporting memories to {input_dir}", flush=True)
    run_exporter(
        input_dir,
        args.limit,
        args.qdrant_url,
        args.collection,
        args.container,
        args.min_similarity,
        args.neighbors_per_node,
    )

    extraction = build_extraction(input_dir)
    n_nodes = len(extraction["nodes"])
    n_edges = len(extraction["edges"])
    print(f"[engram-graph] built extraction: {n_nodes} nodes, {n_edges} edges", flush=True)

    if n_nodes == 0:
        print("[engram-graph] no memories to graph — collection is empty.", file=sys.stderr)
        return 3

    try:
        G = build_from_json(extraction)
        communities = cluster(G)
    except Exception as exc:  # noqa: BLE001
        print(f"[engram-graph] graphify build failed: {exc}", file=sys.stderr)
        return 2

    html_path = graphify_out / "graph.html"
    json_path = graphify_out / "graph.json"

    try:
        to_json(G, communities, str(json_path))
        to_html(G, communities, str(html_path))
    except Exception as exc:  # noqa: BLE001
        print(f"[engram-graph] graphify export failed: {exc}", file=sys.stderr)
        return 2

    print(f"[engram-graph] graph.html: {html_path}")
    print(f"[engram-graph] graph.json: {json_path}")
    print(
        f"[engram-graph] {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges, "
        f"{len(communities)} communities → {html_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
