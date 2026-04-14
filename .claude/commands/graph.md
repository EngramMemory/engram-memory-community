---
description: Generate an interactive visual graph of your memories using graphify
argument-hint: "[--user <id>]"
allowed-tools: Bash, Read
---

Generate an interactive vis.js graph of the Engram memory store by handing
the memories off to the `graphify` CLI (https://github.com/safishamsi/graphify).

Arguments: $ARGUMENTS

Steps:

1. Verify graphify is installed. Run `graphify --version`. If it is missing
   or exits non-zero, tell the user:
   `graphify is not installed. Run: pip install graphifyy` and stop.
2. Create a fresh input directory at
   `~/.engram/graph-input-$(date +%Y%m%d-%H%M%S)` and remember the path.
3. From the repo root, run the export helper into that directory:
   `python scripts/export_memories_for_graph.py --output <input-dir> $ARGUMENTS`.
   If the script prints that the graph is empty, stop and tell the user to
   store some memories first.
4. Invoke graphify on the input directory from the repo root:
   `graphify <input-dir>`. This produces `graphify-out/graph.html` plus
   `graph.json` and `obsidian/` under the current working directory.
5. Report the absolute path to `graphify-out/graph.html` and offer to open
   it (e.g. `xdg-open graphify-out/graph.html` on Linux). Do not open it
   without confirmation.

Do not modify the memory store. Do not invent fake memories. If any step
fails, surface the exact stderr to the user and stop.
