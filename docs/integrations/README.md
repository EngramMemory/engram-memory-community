# Engram Bridge — Agent & IDE Integrations

The Engram Bridge is a small client-side daemon (installed with
`pip install -e ./bridge`) that pulls relevant memories from the
Engram cloud on session start and pushes meaningful local events
(milestones, commits, green test runs) back to the cloud as new
memories. It's designed to be **off unless configured**: if
`~/.engram/config.yaml` is missing or has no valid `api_key`, every
command exits `0` silently and never breaks your workflow.

This directory holds per-agent wiring guides. The general install
and configuration steps live in **[../../bridge/README.md](../../bridge/README.md)**
— read that first, then pick your agent below.

---

## Supported agents

| Agent | Read (pull context) | Push (events) | Team scope | Native MCP |
|---|---|---|---|---|
| [Claude Code](claude-code.md) | yes — `SessionStart` hook | yes — bridge CLI + git hook + pytest plugin | yes | yes |
| [Cursor](cursor.md) | yes — MCP `memory_search` tool | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | yes |
| [Windsurf / Codeium](windsurf.md) | yes — MCP `memory_search` tool | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | yes |
| [Continue](continue-dev.md) | yes — MCP `memory_search` tool | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | yes |
| [Aider](aider.md) | partial — shell alias on session start | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | no |
| [OpenAI Codex CLI](codex.md) | partial — shell alias on session start | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | no |
| [Sourcegraph Cody](cody.md) | manual — paste `engram-bridge pull` output | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | no |
| [Generic MCP client](generic-mcp.md) | on-demand tool call (not session-start) — see note | yes — bridge CLI + git hook + pytest plugin | yes (CLI) | yes |
| [Generic REST / SDK client](generic-rest.md) | yes — any agent that can shell out or call REST | yes — REST `POST /v1/store` | yes (REST) | no |

### Column meaning

- **Read (pull context)** — can the agent automatically load relevant
  Engram memories at the start of a session? A full `yes` means there's
  a native "on session start" hook we wire into. `partial` means the
  agent has no session-start hook but can be wired through a shell
  alias that runs `engram-bridge pull` before launching the agent.
  `manual` means you paste the output of `engram-bridge pull` yourself.
- **Push (events)** — can you push milestones, commits, and green test
  runs back to Engram from inside the agent's workflow? Every agent
  here gets a `yes` because the push path lives in the `engram-bridge`
  CLI itself (plus the git post-commit hook and pytest plugin), and
  those run the same way regardless of which agent you're in.
- **Team scope** — can you `push` into and `pull` from shared team
  collections (Wave 3)? All CLI paths support `--team <id>` on push
  and `--scope team:<id>` on pull. The MCP tools don't yet expose
  team scopes — see the **MCP gap** note below.
- **Native MCP** — does the agent support the Model Context Protocol
  out of the box? If yes, you can point it at the Engram MCP server at
  `mcp/server.py` and get the seven memory tools (`memory_store`,
  `memory_search`, `memory_recall`, `memory_forget`, `memory_consolidate`,
  `memory_feedback`, `memory_connect`) without touching the bridge CLI.

---

## MCP gap (Wave 3 teams)

The Engram MCP server at
[`mcp/server.py`](../../mcp/server.py) exposes seven tools today:

1. `memory_store`
2. `memory_search`
3. `memory_recall`
4. `memory_forget`
5. `memory_consolidate`
6. `memory_feedback`
7. `memory_connect`

None of them accept a `scope` or `team_id` argument yet — the MCP
server currently only reads/writes the per-user collection. If you
need to push to or pull from a shared team, use the bridge CLI:

```bash
engram-bridge push "shipped feature X" --team <team_uuid>
engram-bridge pull --scope team:<team_uuid>
```

Extending the MCP server to advertise team scopes is a follow-up
wave. Until then, MCP clients see personal memory only.

---

## Read path vs push path (quick reference)

```
pull context on session start     →  READ PATH  →  POST /v1/search
push milestone / commit / green   →  PUSH PATH  →  POST /v1/store
list / create / invite a team     →  TEAM PATH  →  /v1/teams/*
```

| Path | Entry points | Cloud endpoint |
|---|---|---|
| read | `engram-bridge pull`, MCP `memory_search` / `memory_recall` | `POST /v1/search` |
| push | `engram-bridge push`, `push-commit`, `push-test`, MCP `memory_store` | `POST /v1/store` |
| team | `engram-bridge team list/create/add-member`, `push --team`, `pull --scope team:<id>` | `GET/POST /v1/teams`, `POST /v1/teams/{id}/members` |

---

## Before you start

Every agent doc assumes:

1. You have an Engram cloud API key that starts with `eng_live_`.
   Grab one from [https://engrammemory.ai](https://engrammemory.ai).
2. You've installed the bridge:
   ```bash
   cd engram-memory-community
   pip install -e ./bridge
   ```
3. You've written a config template and pasted your key:
   ```bash
   engram-bridge install --write-config-template
   $EDITOR ~/.engram/config.yaml   # set api_key
   engram-bridge status            # should print "enabled: yes"
   ```

If `engram-bridge status` doesn't show `enabled: yes` and
`api health: ok`, stop and fix that first. No agent integration will
work until the bridge itself is happy — see the troubleshooting
checklist inside any of the per-agent docs below.
