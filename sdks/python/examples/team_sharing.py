"""End-to-end team sharing flow.

Creates a team, adds a member, stores a memory into it, and then
searches within the team scope. The target user id is read from
argv[1] so the script doesn't hard-code another account.

    export ENGRAM_API_KEY=pr_live_...
    python examples/team_sharing.py <invitee_user_uuid>

If the invitee hasn't signed up yet, the add step returns a 404 —
the SDK surfaces it as ``EngramAPIError`` with status 404 and the
script prints a readable message before exiting.
"""

from __future__ import annotations

import sys

from engram import (
    EngramAPIError,
    EngramClient,
    EngramError,
)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python team_sharing.py <invitee_user_uuid>", file=sys.stderr)
        return 2
    invitee = argv[1]

    client = EngramClient()
    try:
        # 1. Create a team. Slug must be lowercase alphanumeric + hyphens.
        team = client.create_team(name="Platform Ops", slug="platform-ops-demo")
        print("[create]  team={} slug={}".format(team.id, team.slug))

        # 2. Invite a second human.
        try:
            client.add_team_member(team.id, user_id=invitee, role="member")
            print("[add]     member={}".format(invitee))
        except EngramAPIError as exc:
            if exc.status_code == 404:
                print(
                    "Invitee {} not found — they need to sign up first.".format(invitee),
                    file=sys.stderr,
                )
                return 1
            raise

        # 3. Store into both the personal collection and the team one
        #    in a single call. The cloud fans the write out atomically —
        #    if the team write fails the personal write rolls back too.
        stored = client.store(
            "Our primary queue is SQS FIFO as of 2025-Q3",
            category="decisions",
            importance=0.8,
            share_with=["team:{}".format(team.id)],
        )
        print("[store]   id={} status={}".format(stored.id, stored.status))

        # 4. Search within the team scope — should return the memory we
        #    just shared.
        scope = "team:{}".format(team.id)
        hits = client.search(
            "what messaging system does the platform team use",
            top_k=5,
            scope=scope,
        )
        print("[search]  scope={} -> {} hits".format(scope, len(hits.results)))
        for i, hit in enumerate(hits.results, start=1):
            print("  {}. {:.2f}  {}".format(i, hit.score, hit.text[:100]))

        # 5. List every team the caller is in, just to sanity-check.
        teams = client.list_teams()
        print("[list]    caller is a member of {} teams".format(len(teams)))
        for t in teams:
            print("  - {} ({}) role={}".format(t.name, t.slug, t.role or "?"))
    except EngramError as exc:
        print("Engram call failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
