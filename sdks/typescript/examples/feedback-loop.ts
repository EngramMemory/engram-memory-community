/**
 * Feedback loop — teach Engram which results your model actually
 * picked. Every time your LLM picks a subset of search results and
 * discards the rest, call `feedback()` with the IDs. Engram uses
 * the signal to boost selected hot-tier matches, penalize rejected
 * ones, and write PREFERRED_OVER edges in its internal graph — all
 * cost-free to you because your LLM already made the judgment.
 *
 * Run with:
 *   ENGRAM_API_KEY=pr_live_... npx tsx examples/feedback-loop.ts
 */

import { EngramClient } from "../src/index.js";

async function main(): Promise<void> {
  const apiKey = process.env.ENGRAM_API_KEY;
  if (!apiKey) throw new Error("Set ENGRAM_API_KEY first.");

  const client = new EngramClient({ apiKey });

  // Seed a handful of memories so the search has something to rank.
  const ids: string[] = [];
  const seeds = [
    "Staging API deploys through GitHub Actions on every merge to main.",
    "Prod deploys require a manual approval from an on-call engineer.",
    "Hotfixes skip staging via the fast-track workflow (infra/hotfix.yml).",
    "All deploys run the smoke-test suite before promoting traffic.",
  ];
  for (const text of seeds) {
    const r = await client.store({ text, category: "runbook" });
    ids.push(r.id);
  }

  // Search. Imagine your LLM then decides which results actually
  // answer the user's question.
  const query = "how do I deploy a hotfix to production";
  const hits = await client.search({ query, topK: 4 });
  console.log(`Got ${hits.results.length} results for "${query}"`);

  // Suppose the LLM judged results 0 and 2 as useful, 1 as off-topic.
  const selected = [hits.results[0], hits.results[2]].filter(Boolean);
  const rejected = [hits.results[1]].filter(Boolean);

  const fb = await client.feedback({
    query,
    selectedIds: selected.map((r) => r!.id),
    rejectedIds: rejected.map((r) => r!.id),
  });

  console.log("Feedback ingested:", {
    success: fb.success,
    boosted: fb.boosted,
    penalized: fb.penalized,
    edges_added: fb.edges_added,
  });

  // Next time someone asks a similar question, the boosted memories
  // will surface higher in the hot tier. No model finetune required.
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
