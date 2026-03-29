# Engram — SOUL Rules

Your agent's system prompt is yours. We're not going to tell you how to define your agent's identity or behavior — that's your call.

What we can offer is a set of rules that make Engram work the way it was designed to: proactively, not reactively. Without guidance, most agents treat memory as a filing cabinet — they store when told and search when asked. With the right rules, your agent builds understanding over time. It recalls before acting, stores what matters without being prompted, and stops asking questions it already knows the answer to.

Below is our recommended configuration. Take it wholesale, adapt it to your style, or just use the parts that make sense for your workflow. The tools work either way — the rules just make them work better.

---

## Recommended Rules

Adapt these to your agent's configuration (SOUL.md, CLAUDE.md, or equivalent).

```markdown
## ENGRAM — HOW YOU THINK

You have persistent memory across sessions. Use it the way a competent person uses their own memory: automatically, constantly, without being told.

### Before You Do Anything

- **Recall first.** Before starting any task, search memory for relevant context: past decisions, preferences, rules, prior work on this area. The answer to most questions is already stored.
- **Before asking the user:** Search memory. If the answer exists, use it. Don't waste their time re-explaining what they already told you.
- **Before coding or deploying:** Search for relevant rules and past mistakes. They exist because something went wrong before.

### While You Work

- **Notice what matters.** When the user states a preference, makes a decision, shares a fact about their system, or corrects your approach — that's worth storing. You don't need to be told.
- **Store completions.** When you finish a task, store a summary: what was done, what files changed, what decisions were made, what's still pending. Future-you needs this.
- **Store corrections.** When you get something wrong and the user fixes your approach, store what happened and why. Don't make the same mistake twice.

### What to Store

| Signal | Category | Importance |
|--------|----------|------------|
| User corrects your approach | `decision` | 0.9 |
| Architectural decision made | `decision` | 0.8 |
| User states a preference | `preference` | 0.7–0.8 |
| Task completed | `fact` | 0.8 |
| System/infrastructure fact learned | `fact` | 0.7 |
| Person, project, or org context | `entity` | 0.6–0.7 |

### What NOT to Store

- Ephemeral conversation filler ("ok", "thanks", "sounds good")
- Things derivable from code or git history
- Exact file contents (store the insight, not the text)
- Speculative or uncertain information

### The Pattern

```
1. Session starts → recall recent context, active projects, permanent rules
2. User gives task → recall anything relevant to this area
3. Work happens → notice preferences, decisions, corrections
4. Task completes → store completion summary
5. Session ends → everything important is already stored
```

This isn't a feature you turn on. It's how you think.
```

---

## Integration

### Memory Tools Available

| Tool | When to use |
|------|-------------|
| `memory_store` | You learned something worth keeping |
| `memory_search` | You need context before acting |
| `memory_recall` | Automatic context injection (auto-recall handles this) |
| `memory_forget` | Something stored is wrong or outdated |

### Auto-Recall

If `autoRecall` is enabled (default), Engram automatically searches for relevant memories before every response and injects them as context. Your agent doesn't need to explicitly call `memory_search` for basic context — it happens automatically.

Explicit `memory_search` is still useful for targeted queries: "What did we decide about the auth system?" or "What are the deployment rules?"

### Auto-Capture

If `autoCapture` is enabled (default), Engram automatically extracts facts from conversations and stores them. This handles the baseline. The SOUL rules above push the agent to be more intentional — storing completions, corrections, and decisions that auto-capture might miss.

---

## Why This Works

Most memory integrations fail because they treat memory as a feature: "call memory_store when the user says 'remember this.'" That's a filing cabinet, not memory.

Real memory is proactive. You don't decide to remember that your colleague prefers TypeScript — you just do, because you were paying attention. These rules make the agent pay attention.

The difference:
- **Without SOUL rules:** Agent uses memory when explicitly asked. Forgets everything between sessions. Asks the same questions repeatedly.
- **With SOUL rules:** Agent recalls before acting, stores what matters, builds understanding over time. Each session starts where the last one left off.
