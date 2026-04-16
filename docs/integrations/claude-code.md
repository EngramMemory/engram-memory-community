# Claude Code

**Engram Bridge works with Claude Code via a native `SessionStart`
hook** (for the read path) and via the same `engram-bridge` CLI +
git hook + pytest plugin that every other agent uses (for the push
path). Claude Code also speaks MCP natively, so you can optionally
point it at the Engram MCP server for on-demand `memory_search` and
`memory_store` calls in the middle of a session.

This page covers both CLI (`claude`) and the desktop app — they
share `~/.claude/settings.json`, so configuring one configures the
other.

---

## Prerequisites

- Engram cloud API key starting with `eng_live_`
  (grab one at [https://engrammemory.ai](https://engrammemory.ai))
- Bridge installed:
  ```bash
  cd engram-memory-community
  pip install -e ./bridge
  ```
- Config file at `~/.engram/config.yaml` with a valid `api_key`.
  If you don't have one yet:
  ```bash
  engram-bridge install --write-config-template
  $EDITOR ~/.engram/config.yaml   # paste your key
  engram-bridge status            # must print "enabled: yes"
  ```

See **[../../bridge/README.md](../../bridge/README.md)** for the full
install + config walkthrough.

---

## Wiring the read path (`SessionStart` hook)

The bridge ships a one-shot installer that patches
`~/.claude/settings.json`:

```bash
engram-bridge install --claude-code
```

That command:

1. Creates `~/.claude/settings.json` if missing, else takes a
   timestamped `.bak-YYYYMMDD-HHMMSS` backup.
2. Merges a `hooks.SessionStart` entry into the file. The entry
   looks like this (idempotent — running the installer twice is a
   no-op):
   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "matcher": "*",
           "hooks": [
             {
               "type": "command",
               "command": "engram bridge pull",
               "id": "engram-bridge-pull"
             }
           ]
         }
       ]
     }
   }
   ```
3. Leaves any other settings keys untouched.

From then on, every new Claude Code session runs `engram bridge pull`
as a prompt prefix. The pull:

1. Detects the current project (git repo basename → directory name
   fallback).
2. Builds a query from repo name + branch + last commit subject.
3. Probes `GET /health` on `api.engrammemory.ai` with a 2 second
   timeout.
4. Calls `POST /v1/search` with `{query, top_k}` and
   `Authorization: Bearer <api_key>`.
5. Renders the returned hits as a markdown preamble and prints it
   to stdout. Claude Code picks it up as context.

On any failure (no config, bad key, unreachable API, zero results)
the pull exits `0` with empty stdout. Your Claude session starts
normally with no error — the worst case is you lose two seconds and
get no added context.

### Verify the hook is firing

1. Inspect the settings file:
   ```bash
   grep -A 8 engram-bridge-pull ~/.claude/settings.json
   ```
   You should see the `id` and the `command`.

2. Run the pull by hand to confirm the command works end-to-end:
   ```bash
   engram-bridge pull
   ```
   If the bridge is configured and there are any relevant memories,
   you'll see a `## Relevant memories` markdown block on stdout.

3. Start a fresh Claude Code session in a git repo and check the
   first assistant message. If the hook is firing and there's
   context to inject, Claude will reference it.

### Remove the hook

Open `~/.claude/settings.json` and delete the block tagged with
`"id": "engram-bridge-pull"`. The installer deliberately avoids an
`--uninstall` flag — it would have to touch user-modified JSON that
it didn't write, and that's more dangerous than a two-line manual
edit.

---

## Wiring the push path

Three event types push to Engram from a Claude Code workflow:

### 1. Manual milestone push

```bash
engram-bridge push "shipped wave 2 of the bridge"
engram-bridge push "fixed recall-tier fusion regression" --type bugfix
engram-bridge push "deploy blocked on API key rotation" \
    --metadata severity=p1 --metadata owner=eddy
```

Run this whenever you want Claude's future sessions to remember a
decision, a shipped feature, or a known blocker. `--type` defaults
to `milestone`. `--metadata key=value` can be repeated.

### 2. Git post-commit hook

Install once per repo:

```bash
cd ~/code/my-repo
engram-bridge install --git-hooks

# or from anywhere
engram-bridge install --git-hooks --repo ~/code/my-repo
```

The installer writes `.git/hooks/post-commit` with a one-line body:

```sh
#!/bin/sh
# engram-bridge: push-commit
engram-bridge push-commit >/dev/null 2>&1 || true
```

`|| true` is load-bearing — a missing or broken `engram-bridge`
binary will never block a commit. The installer is idempotent,
creates a timestamped backup of any existing `post-commit`, and
detects the `# engram-bridge: push-commit` marker to avoid
double-installing.

Every commit from that point on pushes the short sha, subject,
body, author, branch, and a `git show --stat` summary to Engram.

### 3. pytest plugin

Installing the bridge also registers a `pytest11` entry point, so
the plugin auto-loads anywhere pytest can find the package. On
every green test session (exit 0) it calls `engram-bridge push-test`
with the suite name, wall time, and collected test count.

Disable per-run with `-p no:engram_bridge`, or turn the bridge off
in `~/.engram/config.yaml`.

### 4. Shell wrappers for jest / cargo / go

The bridge deliberately doesn't modify your shell rc. Paste one or
more of these into `~/.bashrc` or `~/.zshrc`:

```sh
engram_npm_test() {
  local start end status
  start=$(date +%s)
  npm test "$@"
  status=$?
  end=$(date +%s)
  if [ "$status" -eq 0 ]; then
    engram-bridge push-test "$(basename "$PWD")" \
        "$((end - start))" "0" --runner jest >/dev/null 2>&1 || true
  fi
  return "$status"
}
alias npmtest=engram_npm_test
```

`--runner` accepts `pytest`, `jest`, `cargo`, `go`, or `custom`.
All wrappers swallow bridge failures with `|| true` and never touch
the runner's exit code.

---

## Wiring hive sharing (Wave 3)

Shared hive collections let you and your co-agents pull from the
same pool of memories. Hive commands go through the bridge CLI:

```bash
# List hives your api_key already belongs to
engram-bridge hive list

# Create a new hive — you become owner + first member in one step
engram-bridge hive create "my-hive" --slug my-hive

# Invite another user (owner/admin only)
engram-bridge hive add-member <hive_uuid> <user_uuid> --role member

# Push a memory to your personal store AND fan it out to a hive
engram-bridge push "shipped feature X" --hive <hive_uuid>

# Pull context from a hive collection instead of personal
engram-bridge pull --scope hive:<hive_uuid>
```

`--hive` and `--scope hive:<id>` pass through to
`POST /v1/store` (`share_with`) and `POST /v1/search` (`scope`)
respectively. The cloud validates that the caller is a member of
each listed hive and returns 403 for any hive they aren't in — the
bridge swallows the error silently, so a revoked membership never
breaks a commit or a session start.

> **Gap:** the `SessionStart` hook always runs `engram bridge pull`
> with no `--scope` override, so it pulls from your personal store.
> If you want a session to pull hive context instead, edit
> `~/.claude/settings.json` and change the hook command to
> `engram bridge pull --scope hive:<hive_uuid>`. A per-project
> `scope` config key is planned for a later wave.

---

## Optional: wire the MCP server

Claude Code speaks MCP. You can register the Engram MCP server in
addition to (or instead of) the bridge's `SessionStart` hook:

```bash
claude mcp add engrammemory -- python /path/to/engram-memory-community/mcp/server.py
```

The server ([`mcp/server.py`](../../mcp/server.py)) exposes seven
tools that Claude Code can call on demand:

- `memory_store` — store text with a category + importance score
- `memory_search` — three-tier search (hot cache → hash → vector)
- `memory_recall` — same as search, higher threshold, for context
- `memory_forget` — delete by id or by search-match
- `memory_consolidate` — merge near-duplicates
- `memory_feedback` — tell Engram which results were useful
- `memory_connect` — discover cross-category links

All seven tools talk to the **local** recall engine (Qdrant +
FastEmbed + hash index), not the cloud. They share nothing with
the bridge's pull/push path except the concept of a memory — if
you want a single source of truth across session-start context and
in-session tool calls, pick the bridge OR the MCP server, not both,
until Wave 5 unifies them.

> **Gap:** the MCP server does not yet expose hive scopes. For hive
> sharing, stick with the bridge CLI as shown above.

---

## Troubleshooting

Run through this checklist in order — the bridge is designed to
fail silently, so `engram-bridge status` is your best friend.

1. **Config file exists?**
   ```bash
   test -f ~/.engram/config.yaml && echo ok || echo missing
   ```
2. **`api_key` set?**
   ```bash
   grep '^api_key:' ~/.engram/config.yaml
   ```
   The value must start with `eng_live_`.
3. **`enabled: true`?**
   ```bash
   grep '^enabled:' ~/.engram/config.yaml
   ```
4. **Bridge reports connected?**
   ```bash
   engram-bridge status
   ```
   You want `enabled: yes` and `api health: ok`.
5. **Recent errors in the log?**
   ```bash
   tail -50 ~/.engram/bridge.log
   ```
   Every failed pull or push is logged here with a timestamp.
   The log is rotated at 256 KB with two backups.

If all five check out and the hook still isn't producing context,
confirm that `~/.claude/settings.json` actually contains the
`engram-bridge-pull` id and that the `command` string matches
exactly (`engram bridge pull`). Start a brand new Claude Code
session — hooks only fire on session start, not on a live reload.
