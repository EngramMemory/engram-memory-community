/**
 * Basic usage: store a memory, search for it, forget it.
 *
 * Run with an API key in your environment:
 *   ENGRAM_API_KEY=pr_live_... npx tsx examples/basic-usage.ts
 *
 * No env-var magic inside the SDK — we read it here at the edge and
 * pass it explicitly. That way the SDK stays pure and this script
 * stays obvious.
 */

import { EngramClient, EngramAuthError, EngramRateLimitError } from "../src/index.js";

async function main(): Promise<void> {
  const apiKey = process.env.ENGRAM_API_KEY;
  if (!apiKey) {
    console.error("Set ENGRAM_API_KEY first.");
    process.exit(1);
  }

  const client = new EngramClient({ apiKey });

  try {
    // 1. Store a memory
    const stored = await client.store({
      text: "Production database is PostgreSQL 16 on Neon, us-east-1.",
      category: "infrastructure",
      importance: 0.9,
      metadata: { source: "architecture-doc", verified: true },
    });
    console.log("Stored:", stored.id, "->", stored.category);

    // 2. Search for it. `topK` maps to the wire-level `limit`.
    const hits = await client.search({
      query: "what database does production use",
      topK: 3,
    });
    console.log(`Got ${hits.results.length} results (${hits.query_tokens} query tokens):`);
    for (const r of hits.results) {
      console.log(` - [${r.score.toFixed(3)}] ${r.text}`);
    }

    // 3. Forget it
    if (hits.results[0]) {
      const gone = await client.forget(hits.results[0].id);
      console.log("Forgot:", gone.status, gone.id);
    }
  } catch (err) {
    // Error classification lets you branch on cause rather than
    // substring-matching error messages.
    if (err instanceof EngramAuthError) {
      console.error("Auth failed — check your API key.");
      process.exit(2);
    }
    if (err instanceof EngramRateLimitError) {
      console.error(
        `Rate limited. Retry after ${err.retryAfter ?? "?"}s. Upgrade at https://app.engrammemory.ai/dashboard/billing`,
      );
      process.exit(3);
    }
    throw err;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
