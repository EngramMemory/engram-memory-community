# @engram/sdk

Official TypeScript SDK for the [Engram Memory](https://engrammemory.ai) API.

Zero runtime dependencies. Works in Node 18+, modern browsers,
Cloudflare Workers, Deno, and Bun. Dual ESM + CJS builds, full
TypeScript definitions.

## Install

```bash
npm install @engram/sdk
# or
pnpm add @engram/sdk
# or
yarn add @engram/sdk
```

## Quick start

```ts
import { EngramClient } from "@engram/sdk";

const client = new EngramClient({ apiKey: process.env.ENGRAM_API_KEY! });

// Store
const { id } = await client.store({
  text: "Prod DB is PostgreSQL 16 on Neon, us-east-1.",
  category: "infrastructure",
  importance: 0.9,
});

// Search
const { results } = await client.search({
  query: "what database does prod use",
  topK: 5,
});

// Forget
await client.forget(id);
```

## Features

- **Memory ops** — `store`, `search`, `forget`, `feedback`
- **Team scopes (Wave 3)** — `createTeam`, `listTeams`, `addTeamMember`,
  `removeTeamMember`, plus `shareWith` on store and `scope` on search
- **Error classification** — `EngramAuthError`, `EngramRateLimitError`,
  `EngramAPIError`, `EngramConnectionError`
- **Retries with backoff** — network errors and transient 5xx retry
  automatically; non-idempotent POSTs never retry
- **Runtime-agnostic** — inject your own `fetch` if you need to

## Client options

```ts
new EngramClient({
  apiKey: "pr_live_...",              // required, no env fallback
  baseUrl: "https://api.engrammemory.ai", // default
  timeout: 30_000,                    // ms, default 30s
  maxRetries: 3,                      // default 3
  retryBackoff: 500,                  // ms base, exponential
  fetch: customFetch,                 // for Workers/Deno/tests
});
```

## Error handling

```ts
import { EngramAuthError, EngramRateLimitError, EngramAPIError } from "@engram/sdk";

try {
  await client.store({ text: "..." });
} catch (err) {
  if (err instanceof EngramAuthError) {
    // 401 — bad or revoked key
  } else if (err instanceof EngramRateLimitError) {
    // 429 — err.retryAfter is seconds (or null)
  } else if (err instanceof EngramAPIError) {
    // other 4xx/5xx — err.status, err.body
  }
}
```

## Team-scoped memory

```ts
const team = await client.createTeam({ name: "Platform", slug: "platform" });

await client.store({
  text: "Staging redis rotates every 90 days.",
  shareWith: [`team:${team.id}`],
});

const { results } = await client.search({
  query: "redis rotation schedule",
  scope: `team:${team.id}`,
});
```

## Feedback loop

Turn your LLM's judgment into a ranking signal — no extra model calls,
no finetune:

```ts
const hits = await client.search({ query });
// ... your LLM picks some results, rejects others ...
await client.feedback({
  query,
  selectedIds: picked.map((r) => r.id),
  rejectedIds: discarded.map((r) => r.id),
});
```

## Examples

See [`examples/`](./examples) for runnable scripts:
- `basic-usage.ts` — store, search, forget
- `team-sharing.ts` — the full Wave 3 team flow
- `feedback-loop.ts` — feedback-driven ranking

## License

MIT
