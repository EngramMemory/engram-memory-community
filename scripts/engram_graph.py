#!/usr/bin/env python3
"""Pure renderer for the /graph slash command.

Two modes:

* ``--mode llm`` (default): read a pre-built ``{nodes, edges}`` JSON file
  produced by the host Claude Code session (the slash-command body does
  entity extraction and relationship mapping itself via the engram MCP
  tools) and render it through the vendored graphify pipeline.

* ``--mode auto``: standalone fallback — scroll the live Qdrant
  collection and build similarity edges from the stored vectors. Used
  for CI and direct CLI invocations where no host LLM is available.

This script NEVER reads an LLM API key and NEVER calls an external LLM.
The only LLM involved in ``llm`` mode is the host Claude that invoked
the slash command; all of its work happens outside this process.

Usage::

    # host-LLM flow (/graph slash command)
    python3 scripts/engram_graph.py --mode llm \\
        --input /path/to/graph-input.json \\
        --output /tmp/engram-graph-run

    # standalone / CI similarity flow
    python3 scripts/engram_graph.py --mode auto --output /tmp/engram-graph-auto

Exit codes:
    0  success — ``graph.html`` was written
    1  exporter / input failure
    2  graphify build or export failure
    3  empty graph (no nodes to render)
"""

from __future__ import annotations

import argparse
import json
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


# ---------------------------------------------------------------------------
# llm mode — read host-LLM-produced JSON and map to graphify schema
# ---------------------------------------------------------------------------

def _trim(text: str, limit: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "\u2026"


def load_llm_input(input_path: Path) -> dict[str, Any]:
    """Read + normalise an LLM-produced graph spec into graphify's format.

    Input schema (loose, produced by the host Claude):
        {
          "nodes": [
            {"id": str, "label": str,
             "category"?: str, "content"?: str, "entities"?: [str, ...]},
            ...
          ],
          "edges": [
            {"source": str, "target": str,
             "type"?: str, "label"?: str, "weight"?: float},
            ...
          ]
        }

    graphify requires on every node: id, label, file_type, source_file.
    graphify requires on every edge: source, target, relation,
    confidence, source_file. We use ``file_type="rationale"`` (the
    graphify bucket for prose) and ``source_file="engram-memory"``.
    """
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[engram-graph] input file not found: {input_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[engram-graph] input file is not valid JSON: {exc}")

    if not isinstance(raw, dict):
        raise SystemExit("[engram-graph] input JSON must be an object with 'nodes' and 'edges'")

    in_nodes = raw.get("nodes")
    in_edges = raw.get("edges", [])
    if not isinstance(in_nodes, list):
        raise SystemExit("[engram-graph] input JSON missing 'nodes' list")
    if not isinstance(in_edges, list):
        raise SystemExit("[engram-graph] input JSON 'edges' must be a list")

    nodes: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i, n in enumerate(in_nodes):
        if not isinstance(n, dict):
            raise SystemExit(f"[engram-graph] node {i} is not an object")
        nid = n.get("id")
        label = n.get("label")
        if not nid or not label:
            raise SystemExit(f"[engram-graph] node {i} missing required 'id' or 'label'")
        nid = str(nid)
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        node: dict[str, Any] = {
            "id": nid,
            "label": _trim(str(label), 60),
            "file_type": "rationale",
            "source_file": "engram-memory",
        }
        if "category" in n and n["category"]:
            node["category"] = str(n["category"])
        if "content" in n and n["content"]:
            node["content"] = _trim(str(n["content"]), 200)
        if "entities" in n and isinstance(n["entities"], list):
            node["entities"] = [str(e) for e in n["entities"] if e]
        nodes.append(node)

    edges: list[dict[str, Any]] = []
    for i, e in enumerate(in_edges):
        if not isinstance(e, dict):
            raise SystemExit(f"[engram-graph] edge {i} is not an object")
        src = e.get("source")
        tgt = e.get("target")
        if not src or not tgt:
            raise SystemExit(f"[engram-graph] edge {i} missing required 'source' or 'target'")
        src, tgt = str(src), str(tgt)
        if src not in seen_ids or tgt not in seen_ids:
            # Silently drop edges that reference unknown nodes — same
            # contract graphify itself uses for dangling edges.
            continue
        edge: dict[str, Any] = {
            "source": src,
            "target": tgt,
            "relation": str(e.get("type") or e.get("relation") or "related"),
            "confidence": "EXTRACTED",
            "source_file": "engram-memory",
        }
        if "label" in e and e["label"]:
            edge["label"] = str(e["label"])
        if "weight" in e:
            try:
                edge["weight"] = float(e["weight"])
            except (TypeError, ValueError):
                pass
        edges.append(edge)

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# auto mode — standalone similarity pipeline
# ---------------------------------------------------------------------------

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


import re  # noqa: E402  (only used by auto mode)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_SCALAR_RE = re.compile(r'^([A-Za-z0-9_]+):\s*"?(.*?)"?\s*$')


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
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


def _summarise(body: str, limit: int = 80) -> str:
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if not first:
        return "(empty memory)"
    if len(first) <= limit:
        return first
    return first[: limit - 1].rstrip() + "\u2026"


def build_extraction_from_export(input_dir: Path) -> dict[str, Any]:
    md_files = sorted(p for p in input_dir.glob("*.md") if not p.name.startswith("_"))
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for md in md_files:
        front, body = parse_markdown(md)
        mem_id = front.get("id") or md.stem
        node = {
            "id": mem_id,
            "label": _summarise(body) if body else _summarise(front.get("id", mem_id)),
            "file_type": "rationale",
            "source_file": md.name,
        }
        for k in ("created_at", "user_id", "tier", "importance", "category"):
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


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render(extraction: dict[str, Any], graphify_out: Path) -> tuple[int, int, int, Path]:
    graphify_out.mkdir(parents=True, exist_ok=True)
    G = build_from_json(extraction)
    communities = cluster(G)
    html_path = graphify_out / "graph.html"
    json_path = graphify_out / "graph.json"
    to_json(G, communities, str(json_path))
    to_html(G, communities, str(html_path))
    return G.number_of_nodes(), G.number_of_edges(), len(communities), html_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Render an engram memory graph via graphify")
    ap.add_argument("--mode", choices=("llm", "auto"), default="llm",
                    help="llm: read host-LLM JSON from --input; auto: scroll Qdrant for similarity edges")
    ap.add_argument("--input", help="Path to host-LLM-produced graph JSON (required for --mode llm)")
    ap.add_argument("--output", required=True, help="Directory where graphify-out/ will be written")
    # auto-mode knobs (ignored in llm mode)
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    ap.add_argument("--collection", default="agent-memory")
    ap.add_argument("--container", default="engram-memory")
    ap.add_argument("--min-similarity", type=float, default=0.5)
    ap.add_argument("--neighbors-per-node", type=int, default=5)
    args = ap.parse_args()

    out_root = Path(args.output).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    graphify_out = out_root / "graphify-out"

    if args.mode == "llm":
        if not args.input:
            print("[engram-graph] --input is required for --mode llm", file=sys.stderr)
            return 1
        input_path = Path(args.input).expanduser().resolve()
        extraction = load_llm_input(input_path)
    else:
        input_dir = out_root / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
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
        extraction = build_extraction_from_export(input_dir)

    n_nodes = len(extraction["nodes"])
    n_edges = len(extraction["edges"])
    if n_nodes == 0:
        print("[engram-graph] no memories to graph — nothing to render.", file=sys.stderr)
        return 3

    try:
        nodes, edges, communities, html_path = render(extraction, graphify_out)
    except Exception as exc:  # noqa: BLE001
        print(f"[engram-graph] graphify build/export failed: {exc}", file=sys.stderr)
        return 2

    print(
        f"[engram-graph] mode={args.mode} nodes={nodes} edges={edges} "
        f"communities={communities} \u2192 {html_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
