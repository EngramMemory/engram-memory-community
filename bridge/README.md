# Engram Bridge

A tiny client-side daemon that pulls relevant memories from the
[Engram cloud](https://engrammemory.ai) and injects them as context at
the start of every agent session.

**Status:** Wave 1 — read path only. The bridge can *pull* memories
into a session but does not yet push new ones. That lands in Wave 2.

---

## Design rules

1. **Off unless configured.** If `~/.engram/config.yaml` is missing, is
   empty, or has no valid `api_key`, every command exits `0` silently.
   A disabled bridge never breaks your workflow.
2. **Never writes to stdout on failure.** All errors go to
   `~/.engram/bridge.log`. Agents get either useful context or nothing
   at all — never a stack trace in their prompt.
3. **Cheap to run.** `pull` hits a 2-second health probe before the
   search call. If the cloud is unreachable, you lose two seconds and
   get zero output.

---

## Install

### From source (community repo)

```bash
cd engram-memory-community
pip install -e ./bridge
```

### From PyPI (once published)

```bash
pip install engram-bridge
```

Either way, the `engram-bridge` console script ends up on your `PATH`.
If you also have the top-level `engram` CLI installed, it will delegate
`engram bridge <cmd>` to this package automatically.

---

## Configure

Create the config template:

```bash
engram-bridge install --write-config-template
```

That writes `~/.engram/config.yaml` with an **empty** `api_key` —
deliberately, so nothing happens until you paste one in:

```yaml
api_key: "eng_live_..."       # paste yours here
api_base: "https://api.engrammemory.ai"
enabled: true

projects:
  default:
    top_k: 8
  # Per-project overrides, keyed by project_id (usually the git
  # repo basename):
  #
  # engram-memory-community:
  #   top_k: 12
```

Then check the state:

```bash
engram-bridge status
```

You should see `enabled: yes` and `api health: ok`.

---

## Wire into Claude Code

```bash
engram-bridge install --claude-code
```

This patches `~/.claude/settings.json` to add a `SessionStart` hook
that runs `engram bridge pull`. It's idempotent (running it twice is a
no-op) and takes a timestamped backup of your existing settings file
before modifying it. Remove the hook by editing the file by hand — it's
marked with `"id": "engram-bridge-pull"` for easy grep-ability.

---

## Commands

| Command | What it does |
|---|---|
| `engram-bridge` | Prints help. |
| `engram-bridge pull` | Pulls memories for the current cwd and prints a markdown preamble. Exits 0 silently if the bridge is disabled, the API is unreachable, or there are zero results. |
| `engram-bridge pull --project foo --top-k 12` | Override the detected `project_id` and/or `top_k`. |
| `engram-bridge status` | Shows config path, enabled state, detected project, query, and a live API health probe. `--json` for machine-readable output. |
| `engram-bridge install --claude-code` | Registers the SessionStart hook (see above). |
| `engram-bridge install --write-config-template` | Creates `~/.engram/config.yaml` from the template. |

---

## Troubleshooting

- **`pull` prints nothing.** That's by design. Check
  `engram-bridge status`; it will tell you exactly why (no config, empty
  `api_key`, unreachable API, or zero results).
- **`~/.engram/bridge.log`** captures every failed pull with a
  timestamp. It's rotated at 256 KB with two backups.
- **The hook isn't firing.** Confirm `~/.claude/settings.json` has a
  `hooks.SessionStart` entry containing `"id": "engram-bridge-pull"`.

---

## How it works

1. On `pull`, the bridge resolves a `project_id` from your cwd (git
   repo basename, falling back to the directory name).
2. It builds a query string from the repo name, current branch, and
   last commit subject.
3. It probes `/v1/health` on the configured `api_base` with a 2-second
   timeout. If that fails, the pull ends silently.
4. It `POST`s to `/v1/search` with `{query, top_k}` and the headers
   `Authorization: Bearer <api_key>` and `X-API-Version: 1`.
5. It renders the returned hits as a markdown preamble and prints it
   to stdout, where Claude Code (or any other hook-friendly agent) can
   pick it up as context.

No telemetry, no background threads, no retry loops. The bridge does
one thing per invocation and then disappears.
