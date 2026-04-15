---
description: Generate an interactive visual graph of your memories. Powered by graphify (github.com/safishamsi/graphify, MIT).
argument-hint: "[--limit <N>]"
allowed-tools: Bash, Read
---

Generate an interactive vis.js graph of the Engram memory store by
exporting every memory from the live engram container and handing it
off to the vendored graphify library under `vendor/graphify/`. No
extra PyPI install is required — graphify ships in-tree.

Arguments: $ARGUMENTS

Steps:

2. Create a fresh output directory at
   `~/.engram/graph-$(date +%Y%m%d-%H%M%S)` and remember the path as
   `<OUT>`.
3. From the repo root, run the driver:
   `python3 scripts/engram_graph.py --output <OUT> $ARGUMENTS`.
   The driver calls `scripts/export_memories_for_graph.py` internally
   to pull memories out of Qdrant, then invokes
   `graphify.build_from_json` / `cluster` / `to_html` / `to_json` from
   `vendor/graphify/`.
4. If the driver exits with code 3, the `agent-memory` collection was
   empty — tell the user to store some memories first and stop.
5. If the driver exits with code 1 or 2, surface the full stderr to
   the user and stop.
6. On success, report the absolute path to `<OUT>/graphify-out/graph.html`
   and offer to open it (e.g. `xdg-open <OUT>/graphify-out/graph.html`
   on Linux). Do not open it without confirmation.

Do not modify the memory store. Do not invent fake memories. The
graph is read-only over the live engram Qdrant collection.
