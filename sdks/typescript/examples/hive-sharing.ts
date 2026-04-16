/**
 * Hive grant-based access example.
 *
 * Demonstrates the grant-based hive lifecycle:
 *   1. Create a hive (caller becomes owner)
 *   2. Grant an API key prefix access to the hive
 *   3. List grants to verify
 *   4. Search the hive scope via `scope: "hive:<uuid>"`
 *   5. Revoke the grant (cleanup)
 *
 * Run with:
 *   ENGRAM_API_KEY=pr_live_... npx tsx examples/hive-sharing.ts
 */

import { EngramClient } from "../src/index.js";

async function main(): Promise<void> {
  const apiKey = process.env.ENGRAM_API_KEY;
  if (!apiKey) {
    throw new Error("Set ENGRAM_API_KEY first.");
  }

  const client = new EngramClient({ apiKey });

  // 1. Create the hive. Slug must be 3-48 chars, lowercase alphanumerics
  //    and hyphens. The caller's own key becomes owner automatically.
  const hive = await client.createTeam({
    name: "Platform Hive",
    slug: `platform-${Date.now().toString(36)}`,
  });
  console.log("Hive created:", hive.id, hive.slug);

  // 2. Grant access to another API key prefix. The key_prefix is the
  //    first few characters of the API key you want to grant access to.
  const keyPrefix = process.env.GRANT_KEY_PREFIX;
  if (keyPrefix) {
    const grant = await client.grantHiveAccess(hive.id, {
      keyPrefix,
      permission: "readwrite",
    });
    console.log("Granted:", grant.key_prefix, "permission:", grant.permission);

    // 3. List all grants on this hive.
    const grants = await client.listHiveGrants(hive.id);
    console.log(`Hive has ${grants.length} grant(s).`);
    for (const g of grants) {
      console.log(`  - ${g.key_prefix} (${g.permission})`);
    }
  }

  // 4. Search the hive's collection. Scope routes the search engine
  //    to the hive's physical Qdrant collection and rechecks access
  //    before returning anything.
  const teamHits = await client.search({
    query: "how do I rotate the redis password",
    scope: `hive:${hive.id}`,
    topK: 5,
  });
  console.log(`Hive scope returned ${teamHits.results.length} result(s).`);

  // 5. Cleanup — revoke the grant if we added one.
  if (keyPrefix) {
    const revoked = await client.revokeHiveAccess(hive.id, keyPrefix);
    console.log("Revoked:", revoked.key_prefix, "=>", revoked.revoked);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
