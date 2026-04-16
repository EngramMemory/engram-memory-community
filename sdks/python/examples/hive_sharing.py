"""End-to-end hive sharing flow.

Creates a hive, adds a member, stores a memory into it, and then
searches within the hive scope. The target user id is read from
argv[1] so the script doesn't hard-code another account.

    export ENGRAM_API_KEY=pr_live_...
    python examples/hive_sharing.py <invitee_user_uuid>

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
        print("usage: python hive_sharing.py <invitee_user_uuid>", file=sys.stderr)
        return 2
    invitee = argv[1]

    client = EngramClient()
    try:
        # 1. Create a hive. Slug must be lowercase alphanumeric + hyphens.
        hive = client.create_hive(name="Platform Ops", slug="platform-ops-demo")
        print("[create]  hive={} slug={}".format(hive.id, hive.slug))

        # 2. Invite a second human.
        try:
            client.add_hive_member(hive.id, user_id=invitee, role="member")
            print("[add]     member={}".format(invitee))
        except EngramAPIError as exc:
            if exc.status_code == 404:
                print(
                    "Invitee {} not found — they need to sign up first.".format(invitee),
                    file=sys.stderr,
                )
                return 1
            raise

        # 3. Store into both the personal collection and the hive one
        #    in a single call. The cloud fans the write out atomically —
        #    if the hive write fails the personal write rolls back too.
        stored = client.store(
            "Our primary queue is SQS FIFO as of 2025-Q3",
            category="decisions",
            importance=0.8,
            share_with=["hive:{}".format(hive.id)],
        )
        print("[store]   id={} status={}".format(stored.id, stored.status))

        # 4. Search within the hive scope — should return the memory we
        #    just shared.
        scope = "hive:{}".format(hive.id)
        hits = client.search(
            "what messaging system does the platform hive use",
            top_k=5,
            scope=scope,
        )
        print("[search]  scope={} -> {} hits".format(scope, len(hits.results)))
        for i, hit in enumerate(hits.results, start=1):
            print("  {}. {:.2f}  {}".format(i, hit.score, hit.text[:100]))

        # 5. List every hive the caller is in, just to sanity-check.
        hives = client.list_hives()
        print("[list]    caller is a member of {} hives".format(len(hives)))
        for t in hives:
            print("  - {} ({}) role={}".format(t.name, t.slug, t.role or "?"))
    except EngramError as exc:
        print("Engram call failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
