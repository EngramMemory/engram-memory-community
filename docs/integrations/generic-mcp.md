# Generic MCP client

**Engram works with any MCP-compatible client via the Engram MCP
server ([`mcp/server.py`](../../mcp/server.py)), reached over
streamable-HTTP at `http://localhost:8585/mcp`.** This page is
for agents not explicitly called out in the other integration
docs — anything that speaks the Model Context Protocol and can
connect to a remote HTTP endpoint.

The MCP server registers 15 tools (10 memory + 5 hive) that run
against the local recall engine (Qdrant + FastEmbed + hash index).
The push path runs alongside it as the `engram-bridge` CLI + git
hook + pytest plugin, exactly as it does for every other agent.

---

## Prerequisites

- Engram cloud API key starting with `eng_live_`
  (grab one at [https://engrammemory.ai](https://engrammemory.ai))
- Bridge installed:
  ```bash
  cd engram-memory
  pip install -e ./bridge
  ```
- `~/.engram/config.yaml` with a valid `api_key`:
  ```bash
  engram-bridge install --write-config-template
  $EDITOR ~/.engram/config.yaml
  engram-bridge status
  ```
- The all-in-one `engrammemory/engram-memory` Docker container
  running locally, exposing its MCP endpoint at
  `http://localhost:8585/mcp`:
  ```bash
  docker run -d --name engram-memory --restart unless-stopped \
      -p 6333:6333 -p 11435:11435 -p 8585:8585 \
      -v engram_data:/data \
      engrammemory/engram-memory:latest
  ```

Full bridge install and config walkthrough lives in
**[../../bridge/README.md](../../bridge/README.md)**.

---

## Wiring the read path

Every MCP client has its own config file, but the server entry
always points at the running container's streamable-HTTP endpoint:

```json
{
  "mcpServers": {
    "engrammemory": {
      "url": "http://localhost:8585/mcp"
    }
  }
}
```

Clients that still speak the legacy SSE transport can use
`http://localhost:8585/sse` instead.

Some clients nest the server under a different key
(`experimental.modelContextProtocolServers` for Continue, a
`transport` object for others) — check your client's docs for the
exact schema. The **one field that matters** is always the
endpoint URL: `http://localhost:8585/mcp` (or the legacy
`http://localhost:8585/sse`).

### Tools advertised by the server

Once the server is connected, the client sees 15 tools. The 10
memory tools are:

| Tool | Purpose |
|---|---|
| `memory_store` | Store a memory with `text`, `category` (`preference` / `fact` / `decision` / `entity` / `other`), and `importance` (0-1) |
| `memory_search` | Three-tier search (hot cache → hash → vector) for a free-form `query`, optional `limit` and `category` filter |
| `memory_get` | Fetch a single memory by `memory_id` |
| `memory_timeline` | List memories in chronological order |
| `memory_recall` | Same as search, tuned for context injection — use this on turn 1 for "what do you know about this task" |
| `memory_forget` | Delete by `memory_id` (UUID) or by `query` (deletes the best match) |
| `memory_consolidate` | Janitor: merge near-duplicate memories at a fixed 0.95 similarity threshold (Community tier) |
| `memory_feedback` | Tell Engram which search results were useful — improves future recall ranking at zero cost |
| `memory_connect` | Discover cross-category links for a memory; capped at 3 connections per call on the Community tier |
| `memory_answer` | Answer a free-form question using stored memories |

Plus 5 `hive_*` tools that require an `ENGRAM_API_KEY`:

| Tool | Purpose |
|---|---|
| `hive_list` | List hives the API key can access |
| `hive_create` | Create a new hive |
| `hive_grant` | Grant another API key access to a hive |
| `hive_revoke` | Revoke a key's access to a hive |
| `hive_grants_list` | List the grants on a hive |

The full JSON schema for every tool is at the top of
[`mcp/server.py`](../../mcp/server.py) in the `_register_tools`
method (look for the `Tool(...)` entries).

### Important: MCP doesn't do "session start"

Unlike Claude Code's `SessionStart` hook, MCP tools are called
**on demand** by the agent — only when the model decides to use
them. That means the read path is opt-in per message. You get
"pull context at the start of every new chat" behavior by:

1. Writing a system-prompt rule for your client that tells the
   agent to call `memory_recall` on turn 1, or
2. Wrapping your agent's launcher in a shell alias that runs
   `engram-bridge pull` and stuffs the output into a scratch
   file (`.engram-context.md`) that your system prompt references,
   or
3. Accepting that "search memory" is a verb the user (or a
   higher-level orchestrator) invokes explicitly, the way they'd
   invoke any other tool.

For most MCP clients the rule approach is the least invasive.

---

## Wiring the push path

The push path is agent-agnostic — it runs alongside, not inside,
your MCP client. Every push helper is the same `engram-bridge`
CLI that every other integration uses.

### 1. Manual milestone push

```bash
engram-bridge push "chose duckdb over sqlite for the report layer"
engram-bridge push "user wants all JSON columns typed, never raw" \
    --type preference
```

### 2. Git post-commit hook

```bash
cd ~/code/my-repo
engram-bridge install --git-hooks
```

Writes `.git/hooks/post-commit` with a one-line
`engram-bridge push-commit` call. Idempotent; safe on repos with
existing hooks.

### 3. pytest plugin

Auto-loads via `pytest11` entry point after `pip install -e ./bridge`.
Every green pytest session pushes a `test_pass` event.

### 4. Shell wrappers for jest / cargo / go

```sh
engram_go_test() {
  local start end status
  start=$(date +%s)
  go test "$@"
  status=$?
  end=$(date +%s)
  if [ "$status" -eq 0 ]; then
    engram-bridge push-test "$(basename "$PWD")" \
        "$((end - start))" "0" --runner go >/dev/null 2>&1 || true
  fi
  return "$status"
}
alias gotest=engram_go_test
```

Change `go`/`go` for `npm`/`jest` or `cargo`/`cargo` as needed —
all four are valid `--runner` values.

---

## Wiring hive sharing (Wave 3)

```bash
engram-bridge hive list
engram-bridge hive create "my-hive" --slug my-hive
engram-bridge hive add-member <hive_uuid> <user_uuid> --role member
engram-bridge push "shipped feature X" --hive <hive_uuid>
engram-bridge pull --scope hive:<hive_uuid>
```

> **Gap:** the MCP server advertises `memory_store`,
> `memory_search`, and `memory_recall` without a `scope` or
> `hive_id` argument. Hive reads and writes have to go through
> the bridge CLI (`engram-bridge push --hive ...`, `pull --scope
> hive:...`) until a later wave adds scope to the MCP tool
> schemas. The server does not error on hive calls — it simply
> has no hive code path, so every tool call today hits the
> per-user personal collection.

---

## Troubleshooting

1. **Config file exists?**
   `test -f ~/.engram/config.yaml && echo ok || echo missing`
2. **`api_key` set?** Must start with `eng_live_`.
3. **`enabled: true`** in `~/.engram/config.yaml`?
4. **`engram-bridge status`** says `api health: ok`?
5. **Bridge log clean?** `tail -50 ~/.engram/bridge.log`

MCP-specific checks:

- If your client can't connect to `engrammemory`, confirm the
  container is running and the MCP endpoint is reachable:
  ```bash
  docker ps | grep engram-memory
  curl -s http://localhost:8585/health
  ```
  A healthy container responds on `http://localhost:8585/mcp`.
- If the health check fails, check the container logs:
  ```bash
  docker logs engram-memory
  ```
  Look for `Engram MCP Server initialized` and `Recall engine
  warmed up`.
- If your client only supports stdio, you can bridge to the
  container's server with
  `docker exec -i engram-memory python /app/mcp_server.py`, but
  prefer the HTTP endpoint above.
