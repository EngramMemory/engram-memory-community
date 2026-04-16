# Claude Desktop

**Claude Desktop supports local MCP servers natively.** Add your
Engram Memory MCP server to the desktop config and restart — you
get all seven memory tools (`memory_store`, `memory_search`,
`memory_recall`, `memory_forget`, `memory_consolidate`,
`memory_feedback`, `memory_connect`) directly in conversation.

---

## Prerequisites

- Engram Memory container running locally:
  ```bash
  docker run -d --name engram-memory \
      -p 8585:8585 \
      -v engram-data:/data \
      engrammemory/engram-memory:latest
  ```
- Verify it's up: `curl -s http://localhost:8585/health`

---

## Configure Claude Desktop

The config file lives at:

| OS | Path |
|---|---|
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Linux** | `~/.config/claude/claude_desktop_config.json` |

Add the Engram MCP server entry:

```json
{
  "mcpServers": {
    "engrammemory": {
      "url": "http://localhost:8585/mcp"
    }
  }
}
```

If the file already has other MCP servers, merge the `engrammemory`
key into the existing `mcpServers` object.

Restart Claude Desktop. You should see the Engram tools available
in the tool picker.

### Alternative: one-command install

```bash
npx -y install-mcp@latest http://localhost:8585/mcp \
    --client claude-desktop --name engrammemory --oauth=no -y
```

This writes the config entry for you.

---

## Using Engram in Claude Desktop

Once connected, Claude Desktop can call Engram tools mid-conversation:

- **Store a memory**: Claude calls `memory_store` to save decisions,
  preferences, facts, or anything worth remembering.
- **Search memories**: `memory_search` does three-tier semantic
  search (hot cache, hash index, vector).
- **Recall context**: `memory_recall` is the same as search but
  tuned for broader context injection.
- **Give feedback**: `memory_feedback` tells Engram which results
  were actually useful, improving future recall.

All tools talk to the **local** Engram instance. If the cloud API
is configured (`ENGRAM_API_KEY` set in the container), the recall
engine falls back to cloud on local misses — giving you access to
hive-shared memories from other agents.

### Tip: add a system prompt

For the best experience, add instructions to your Claude Desktop
project or conversation:

```
You have persistent memory via Engram. Use memory_search before
answering questions that might have stored context. Use
memory_store to save important decisions, preferences, and facts.
```

---

## Hive access

If your Engram container is configured with a cloud API key that
has hive grants, searches automatically fall back to hive-scoped
cloud memories when local results are insufficient. This means
your Claude Desktop conversations can benefit from memories stored
by other agents (Claude Code, ChatGPT, Cursor, etc.) that share
the same hive.

No special configuration is needed — hive access is determined by
the API key's grants on the cloud side.

---

## Shared config with Claude Code

Claude Desktop and Claude Code share `~/.claude/` on the same
machine. If you've already configured Engram as an MCP server in
Claude Code:

```bash
claude mcp add engrammemory -- python /path/to/mcp/server.py
```

…the server is available to both. However, Claude Desktop uses
`claude_desktop_config.json` (not `settings.json`), so you need
the entry in both files for both apps to see it.

---

## Troubleshooting

1. **Tools not showing up?** Restart Claude Desktop after editing
   the config. Check the config file is valid JSON.
2. **Connection refused?** Verify the container is running:
   `docker ps | grep engram-memory`
3. **Health check fails?** Check the port mapping:
   `curl http://localhost:8585/health`
4. **Wrong port?** If you changed the container port, update the
   `url` in the config to match.
