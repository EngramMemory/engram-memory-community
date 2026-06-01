# Windsurf / Codeium

**Engram Bridge works with Windsurf (Codeium's AI IDE) via MCP plus
the `engram-bridge` CLI + git hook + pytest plugin for the push
path.** Windsurf's Cascade agent supports MCP natively, so the
`memory_store` / `memory_search` / `memory_recall` tools from the
Engram MCP server ([`mcp/server.py`](../../mcp/server.py)) light up
in the Cascade tool panel as soon as you point it at the container's
HTTP endpoint.

Like Cursor, Windsurf has no built-in "on session start" hook, so
pulling context at the start of a chat is done one of two ways:

1. A Cascade workflow / rule that tells the agent to call
   `memory_recall` on turn 1.
2. A shell alias that runs `engram-bridge pull` before launching
   Windsurf.

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
- The Engram container running locally so Windsurf can connect to
  its MCP endpoint at `http://localhost:8585/mcp`.

Full bridge install and config walkthrough lives in
**[../../bridge/README.md](../../bridge/README.md)**.

---

## Wiring the read path (MCP server)

Windsurf reads MCP config from `~/.codeium/windsurf/mcp_config.json`.
Open that file (create it if it doesn't exist) and add an
`engrammemory` entry:

```json
{
  "mcpServers": {
    "engrammemory": {
      "url": "http://localhost:8585/mcp"
    }
  }
}
```

Restart Windsurf. In Cascade's tool panel you should see the
10 Engram memory tools:

- `memory_store`
- `memory_search`
- `memory_get`
- `memory_timeline`
- `memory_recall`
- `memory_forget`
- `memory_consolidate`
- `memory_feedback`
- `memory_connect`
- `memory_answer`

The server also registers 5 `hive_*` tools (`hive_list`,
`hive_create`, `hive_grant`, `hive_revoke`, `hive_grants_list`)
that require an `ENGRAM_API_KEY`.

### Telling Cascade to use the tools

Windsurf's global and workspace rules live in the Cascade settings
pane under "Rules". Add:

```
On the first turn of every new conversation, call `memory_recall`
with a summary of the task the user just described. Use what
comes back as background context. Don't tell the user you
checked — stay quiet on empty results.

When you finish a non-trivial task, call `memory_store` with a
one-sentence outcome. Categories: `decision` for design choices,
`fact` for reproducible results, `preference` for user
preferences, and `other` otherwise.
```

### Alternative: `engram-bridge pull` on launch

If you'd rather preload context before the agent even starts,
wrap `windsurf` in a shell function that shells out to the bridge
first:

```sh
windsurf_with_memory() {
  local out
  out=$(engram-bridge pull 2>/dev/null || true)
  if [ -n "$out" ]; then
    printf '%s\n' "$out" > .engram-context.md
  fi
  windsurf "$@"
}
alias windsurf=windsurf_with_memory
```

A Cascade rule can then instruct the agent to read
`.engram-context.md` on turn 1. Since `engram-bridge pull` exits
`0` silently when the bridge is off or the API is unreachable, the
alias is free to run on every launch.

---

## Wiring the push path

Identical to every other agent — nothing Windsurf-specific.

### 1. Manual milestone push

```bash
engram-bridge push "refactored Cascade prompt for fewer retries"
engram-bridge push "bug: tool panel doesn't re-render after MCP restart" \
    --type bugfix --metadata severity=p2
```

### 2. Git post-commit hook

```bash
cd ~/code/my-repo
engram-bridge install --git-hooks
```

Writes `.git/hooks/post-commit` with:

```sh
#!/bin/sh
# engram-bridge: push-commit
engram-bridge push-commit >/dev/null 2>&1 || true
```

Idempotent; backs up any existing hook before writing.

### 3. pytest plugin

Auto-loads via the `pytest11` entry point that `pip install -e ./bridge`
registers. Disable per-run with `-p no:engram_bridge`.

### 4. Shell wrappers for jest / cargo / go

```sh
engram_cargo_test() {
  local start end status
  start=$(date +%s)
  cargo test "$@"
  status=$?
  end=$(date +%s)
  if [ "$status" -eq 0 ]; then
    engram-bridge push-test "$(basename "$PWD")" \
        "$((end - start))" "0" --runner cargo >/dev/null 2>&1 || true
  fi
  return "$status"
}
alias cargotest=engram_cargo_test
```

Change `cargo` → `npm` / `go` and the runner flag to match. The
wrapper swallows bridge failures with `|| true` and never touches
the test runner's exit code.

---

## Wiring hive sharing (Wave 3)

```bash
engram-bridge hive list
engram-bridge hive create "windsurf-hive" --slug windsurf-hive
engram-bridge hive add-member <hive_uuid> <user_uuid> --role member
engram-bridge push "picked Remix for the new app" --hive <hive_uuid>
engram-bridge pull --scope hive:<hive_uuid>
```

If you use the `windsurf_with_memory` launcher, change its pull
command to `engram-bridge pull --scope hive:<uuid>` to pin the
context-preload step to a specific hive collection.

> **Gap:** the Engram MCP server does not yet expose hive scopes.
> `memory_search` from inside Cascade only hits your personal
> collection. Hive reads go through the bridge CLI until a later
> wave adds `scope` as an MCP tool argument.

---

## Troubleshooting

1. **Config file exists?**
   `test -f ~/.engram/config.yaml && echo ok || echo missing`
2. **`api_key` set?** Must start with `eng_live_`.
3. **`enabled: true`** in `~/.engram/config.yaml`?
4. **`engram-bridge status`** says `api health: ok`?
5. **Bridge log clean?** `tail -50 ~/.engram/bridge.log`

Windsurf-specific checks:

- In Windsurf's Cascade tool panel, is `engrammemory` listed with
  a green dot? A red dot means Cascade couldn't reach the MCP
  endpoint. Confirm the Engram container is running and that
  `http://localhost:8585/mcp` is reachable (`curl -s
  http://localhost:8585/health`).
- If the container is up but the tools don't appear, verify the
  port mapping and that nothing else is bound to `8585`, then
  restart Windsurf.
- If Cascade's memory tool calls succeed but the push path from
  the terminal is silent, the two config surfaces don't talk:
  the MCP server reads `ENGRAM_API_KEY` from `mcp_config.json`,
  the bridge reads `api_key` from `~/.engram/config.yaml`. Keep
  both in sync.
