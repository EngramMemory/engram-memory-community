/**
 * Team-sharing example — Wave 3 APIs.
 *
 * Demonstrates the full team lifecycle:
 *   1. Create a team (caller becomes owner)
 *   2. Add a member by their user_id
 *   3. Store a memory into the team's scope via `shareWith`
 *   4. Search the team scope via `scope: "team:<uuid>"`
 *   5. Remove the member (optional cleanup)
 *
 * Run with:
 *   ENGRAM_API_KEY=pr_live_... npx tsx examples/team-sharing.ts
 */

import { EngramClient, EngramAPIError } from "../src/index.js";

async function main(): Promise<void> {
  const apiKey = process.env.ENGRAM_API_KEY;
  if (!apiKey) {
    throw new Error("Set ENGRAM_API_KEY first.");
  }

  const client = new EngramClient({ apiKey });

  // 1. Create the team. Slug must be 3-48 chars, lowercase alphanumerics
  //    and hyphens. The caller's own user becomes owner automatically.
  const team = await client.createTeam({
    name: "Platform Team",
    slug: `platform-${Date.now().toString(36)}`,
  });
  console.log("Team created:", team.id, team.slug);

  // 2. Add a second user. You need their Engram user UUID (not email).
  //    This call requires the caller to be owner or admin.
  const collaboratorId = process.env.COLLAB_USER_ID;
  if (collaboratorId) {
    try {
      const added = await client.addTeamMember(team.id, {
        userId: collaboratorId,
        role: "member",
      });
      console.log("Added:", added.user_id, "as", added.role);
    } catch (err) {
      if (err instanceof EngramAPIError && err.status === 404) {
        console.warn("User not found, skipping.");
      } else {
        throw err;
      }
    }
  }

  // 3. Store a memory that fans out to the team collection. The
  //    primary write still lands in the caller's personal collection;
  //    team fanout happens alongside with the same doc_id so it's
  //    addressable from either scope.
  const shared = await client.store({
    text: "Staging redis password rotates every 90 days — script in infra/rotate.sh.",
    category: "runbook",
    importance: 0.8,
    shareWith: [`team:${team.id}`],
  });
  console.log("Stored in personal + team:", shared.id);

  // 4. Search the team's collection specifically. Scope routes the
  //    search engine to the team's physical Qdrant collection and
  //    rechecks membership before returning anything.
  const teamHits = await client.search({
    query: "how do I rotate the redis password",
    scope: `team:${team.id}`,
    topK: 5,
  });
  console.log(`Team scope returned ${teamHits.results.length} result(s).`);

  // 5. Cleanup — remove the collaborator if we added one. Owners
  //    cannot remove themselves; for a full tear-down you'd delete
  //    the team entirely (not yet exposed in this SDK surface).
  if (collaboratorId) {
    const removed = await client.removeTeamMember(team.id, collaboratorId);
    console.log("Removed:", removed.user_id, "=>", removed.removed);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
