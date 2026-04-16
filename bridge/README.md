# Engram Bridge

A tiny client-side daemon that pulls relevant memories from the
[Engram cloud](https://engrammemory.ai) and injects them as context at
the start of every agent session.

**Status:** Wave 2 — read + push. The bridge now *pulls* context at
session start and *pushes* events (manual milestones, git commits,
green test suites) as new memories. Cross-agent sync and hive scopes
land in Wave 3.

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
| `engram-bridge install --git-hooks [--repo PATH]` | Installs a `post-commit` hook that pushes each commit to Engram. Idempotent; merges into any existing hook. |
| `engram-bridge install --write-config-template` | Creates `~/.engram/config.yaml` from the template. |
| `engram-bridge push "<message>" [--type TYPE] [--metadata k=v]...` | Pushes a manual milestone memory. |
| `engram-bridge push-commit [--repo PATH]` | Pushes the current HEAD commit. Normally invoked from the git post-commit hook. |
| `engram-bridge push-test <suite> <duration> <count> [--runner ...]` | Pushes a green test-suite event. |

---

## Push events

Wave 2 turns meaningful local events into memories on the cloud side.
Every push helper obeys the same "off unless configured" rule as the
read path — a disabled bridge never breaks a commit, a test run, or a
user's shell.

### Event types

| Type | Trigger | Content | Metadata includes |
|---|---|---|---|
| `milestone` | `engram-bridge push "<msg>"` | Free-form text | `manual=true`, project context, user-provided `--metadata` |
| `commit` | git `post-commit` hook, manual `push-commit` | `commit <short-sha>: <subject>` + body + `git show --stat` summary | `sha`, `short_sha`, `subject`, `author`, `branch`, `files_changed[]`, `file_count`, `repo_root` |
| `test_pass` | pytest plugin, shell wrappers | `<suite> passed: <count> tests in <duration>s (<runner>)` | `suite`, `duration_seconds`, `test_count`, `runner` |

Every push is additionally stamped with:

- `event_type` — the row above
- `source` — always `engram-bridge`
- `project_id`, `cwd`, `repo_root`, `branch` — same fields the pull
  path uses to build its query, so a read finds what a write stored

### Manual push

```bash
engram-bridge push "shipped wave 2 of the bridge"
engram-bridge push "fixed recall-tier fusion regression" --type bugfix
engram-bridge push "deploy blocked on API key rotation" \
    --metadata severity=p1 --metadata owner=eddy
```

`--type` defaults to `milestone`. `--metadata key=value` can be
repeated; malformed pairs are silently dropped rather than failing
the push.

### Git post-commit hook

```bash
# inside the repo you want tracked
engram-bridge install --git-hooks

# or from anywhere
engram-bridge install --git-hooks --repo ~/code/my-repo
```

The installer writes `.git/hooks/post-commit` (creating it if absent,
merging our block into any existing hook with a timestamped backup).
The hook body is deliberately tiny:

```sh
#!/bin/sh
# engram-bridge: push-commit
engram-bridge push-commit >/dev/null 2>&1 || true
```

The `|| true` is load-bearing — if the `engram-bridge` binary is
missing, errors out, or hangs, the commit still succeeds. The installer
is idempotent: re-running it detects the `# engram-bridge: push-commit`
marker and does nothing.

### pytest plugin

Installing `engram-bridge` also registers a pytest plugin via a
`pytest11` entry point, so the plugin auto-loads anywhere pytest can
find the package. On every green test session (`exitstatus == 0`) it
pushes a `test_pass` event with the suite name (basename of rootdir),
total wall time, and collected test count.

Disable per-run with `-p no:engram_bridge` or by turning the bridge
off in `~/.engram/config.yaml`.

### Shell wrappers for non-pytest runners

The bridge does NOT modify your shell config automatically. Paste one
or more of the following aliases into your `~/.bashrc` or `~/.zshrc`
to hook `npm test`, `cargo test`, or `go test` into the push path:

```sh
# npm test (jest)
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

# cargo test
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

# go test
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

These wrappers swallow any bridge failure (`|| true`) and never
change the test runner's exit code. If you want the shell alias to
*replace* the real command name (e.g. `alias npm=engram_npm_test`),
you can — the wrapper forwards `$@` and returns the original status.

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
3. It probes `/health` on the configured `api_base` with a 2-second
   timeout. (This is the public reachability endpoint — no auth — so
   a rotated key never looks like an outage.)
4. It `POST`s to `/v1/search` with `{query, top_k}` and the headers
   `Authorization: Bearer <api_key>` and `X-API-Version: 1`.
5. It renders the returned hits as a markdown preamble and prints it
   to stdout, where Claude Code (or any other hook-friendly agent) can
   pick it up as context.
6. On `push`, `push-commit`, or `push-test`, it `POST`s to `/v1/store`
   with `{text, category, importance, metadata, collection}`, stamping
   the same project context on every event so the read side finds
   what the write side stored.

No telemetry, no background threads, no retry loops. The bridge does
one thing per invocation and then disappears.
