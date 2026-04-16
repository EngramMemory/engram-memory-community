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
- **Hive access** — `createTeam`, `listTeams`, `grantHiveAccess`,
  `revokeHiveAccess`, `listHiveGrants`, plus `scope` on search
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

## Hive-scoped memory

```ts
const hive = await client.createTeam({ name: "Platform", slug: "platform" });

// Grant an API key prefix access to the hive.
await client.grantHiveAccess(hive.id, { keyPrefix: "eng_live_abc" });

// Search the hive collection.
const { results } = await client.search({
  query: "redis rotation schedule",
  scope: `hive:${hive.id}`,
});

// Revoke access.
await client.revokeHiveAccess(hive.id, "eng_live_abc");
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
- `hive-sharing.ts` — the full Wave 3 hive flow
- `feedback-loop.ts` — feedback-driven ranking

## License

MIT
