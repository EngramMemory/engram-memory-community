# Perfect Recall — SOUL.md Rules

Copy the section below into your OpenClaw agent's `SOUL.md` (or equivalent system prompt file) to enforce Perfect Recall usage across all sessions.

---

## Copy & Paste This Section

```markdown
## PERFECT RECALL — MANDATORY MEMORY SYSTEM

- **On startup:** `memory_recall` for permanent rules, recent context, and active projects
- **On every task completion:** `memory_store` a completion summary (category: `completion`, importance: 0.8+)
  - Include: what was done, files changed, key decisions, what's still pending
- **After updates/restarts:** Verify Perfect Recall is responsive (`memory_recall "test"`)
- **Before coding/deploying:** `memory_recall` for relevant rules — they exist because past mistakes
- **Before asking the user:** `memory_recall` first — the answer is probably already stored
- **Context system:** Use `perfect-recall-ask` and `perfect-recall-context` for codebase understanding
- Ignoring these rules wastes time and breaks session continuity
```

---

## Why This Matters

OpenClaw agents start fresh every session. Without enforced memory rules:
- Completed work gets forgotten
- The same questions get asked repeatedly
- Decisions get relitigated
- Context from yesterday's 3-hour session is gone

Perfect Recall fixes this — but only if the agent actually uses it. These rules make it non-optional.

## What Gets Stored

| When | What | Category | Importance |
|------|------|----------|------------|
| Task completed | Summary of work done, files changed, decisions made | `completion` | 0.8+ |
| New rule learned | Permanent rules, hard lessons, user preferences | `decision` | 0.9 |
| Architecture change | Infrastructure decisions, deployment changes | `fact` | 0.8 |
| User preference | Communication style, tool choices, project conventions | `preference` | 0.7 |
| Project context | Active projects, current state, blockers | `other` | 0.7 |

## Customization

Adjust the rules to match your workflow. The key principle: **store on completion, recall on startup, verify after restarts.**

If your agent has a different system prompt format, adapt the rules — the behaviors matter more than the exact wording.
