# Generic REST / SDK client

**Engram works with any non-MCP agent via the public REST API** —
and by extension, via any HTTP client in any language. This page
is for AI agents, orchestrators, or workflows that can't speak
MCP and can't use a hook-based read path. Think: cron jobs,
custom workflow runners, n8n nodes, in-house agents, Python
scripts, or TypeScript services that want to read and write
Engram directly.

If the other agent docs point you at `engram-bridge pull` or
`engram-bridge push`, this doc does the same thing without the
bridge in the middle: you talk to `POST /v1/store`,
`POST /v1/search`, and `/v1/hives/*` yourself.

---

## What you get

- Read path → `POST /v1/search`
- Push path → `POST /v1/store`
- Hive management → `/v1/hives`, `/v1/hives/{hive_id}/members`
- Health probe (no auth) → `GET /health`

Every authenticated endpoint uses a bearer token on the
`Authorization` header:

```
Authorization: Bearer eng_live_...
X-API-Version: 1
Content-Type: application/json
```

---

## Prerequisites

- Engram cloud API key starting with `eng_live_`
  (grab one at [https://engrammemory.ai](https://engrammemory.ai))
- Any HTTP client. All the examples below work with `curl`, plain
  `httpx` in Python, or `fetch` in TypeScript.

You do **not** need to install `pip install -e ./bridge` to use
this path — the bridge is just a convenience layer on top of the
same REST API you're about to call directly. Install the bridge
only if you want its git hook, pytest plugin, and config
management features.

---

## Prefer a typed client?

If you're writing TypeScript / JavaScript, the
[`@engram/sdk`](../../sdks/typescript/README.md) package wraps the
same REST endpoints with a typed client, retries with backoff,
and classified errors (`EngramAuthError`, `EngramRateLimitError`,
`EngramAPIError`, `EngramConnectionError`). Install it with:

```bash
npm install @engram/sdk
```

Then the read/push/hive examples below become:

```ts
import { EngramClient } from "@engram/sdk";

const client = new EngramClient({
  apiKey: process.env.ENGRAM_API_KEY!,
});

// Read
const { results } = await client.search({
  query: "retry strategy",
  topK: 5,
  scope: "personal",                        // or "hive:<uuid>"
});

// Push
const { id } = await client.store({
  text: "shipped feature X",
  category: "decision",
  importance: 0.6,
  shareWith: ["hive:<uuid>"],               // optional fan-out
});

// Hive
const hive = await client.createTeam({ name: "my-hive", slug: "my-hive" });
const mine = await client.listTeams();
await client.addHiveMember({
  hiveId: hive.id,
  userId: "<user_uuid>",
  role: "member",
});
```

See [`sdks/typescript/README.md`](../../sdks/typescript/README.md)
for the full API surface, error model, and runnable examples
under [`sdks/typescript/examples/`](../../sdks/typescript/examples/).
Python, Go, and other languages talk to the raw HTTP endpoints
shown below — the SDK is TypeScript-only today.

---

## The read path

### Health probe (no auth)

```bash
curl -sS https://api.engrammemory.ai/health
```

Returns HTTP 200 with a small JSON blob when the cloud API is
reachable. This is the same endpoint the bridge uses as its
pre-search reachability probe.

### Search

```bash
curl -sS https://api.engrammemory.ai/v1/search \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how did we handle retries in the httpx client?",
    "top_k": 5
  }'
```

Response shape (abridged):

```json
{
  "results": [
    {
      "id": "...",
      "content": "...",
      "category": "decision",
      "score": 0.87,
      "confidence": 0.91,
      "match_context": "...",
      "tier": "vector",
      "importance": 0.6,
      "timestamp": "...",
      "metadata": { ... }
    }
  ],
  "query_tokens": 12
}
```

Pass `"scope": "hive:<hive_id>"` to search a shared hive
collection instead of your personal one (see Wave 3 below).

### Python example

```python
import os
import httpx

API = "https://api.engrammemory.ai"
KEY = os.environ["ENGRAM_API_KEY"]

headers = {
    "Authorization": f"Bearer {KEY}",
    "X-API-Version": "1",
    "Content-Type": "application/json",
    "User-Agent": "my-agent/1.0",
}

def search(query: str, top_k: int = 5, scope: str = "personal"):
    with httpx.Client(timeout=4.0) as http:
        resp = http.post(
            f"{API}/v1/search",
            headers=headers,
            json={"query": query, "top_k": top_k, "scope": scope},
        )
        resp.raise_for_status()
        return resp.json()["results"]
```

### TypeScript example

```ts
const API = "https://api.engrammemory.ai";
const KEY = process.env.ENGRAM_API_KEY!;

const headers = {
  Authorization: `Bearer ${KEY}`,
  "X-API-Version": "1",
  "Content-Type": "application/json",
  "User-Agent": "my-agent/1.0",
};

export async function search(query: string, top_k = 5, scope = "personal") {
  const res = await fetch(`${API}/v1/search`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, top_k, scope }),
  });
  if (!res.ok) throw new Error(`search failed: ${res.status}`);
  const json = (await res.json()) as { results: unknown[] };
  return json.results;
}
```

---

## The push path

### Store a memory

```bash
curl -sS https://api.engrammemory.ai/v1/store \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "shipped feature X: moved from aiohttp to httpx",
    "category": "decision",
    "importance": 0.6,
    "metadata": {
      "project_id": "my-repo",
      "branch": "main",
      "source": "my-agent",
      "event_type": "milestone"
    },
    "collection": "agent-memory"
  }'
```

Categories: `preference`, `fact`, `decision`, `entity`, or
`other`. Importance is a float 0-1. `metadata` is a free-form
object — stamp anything you want the read side to be able to
filter on.

Response:

```json
{
  "id": "...",
  "status": "stored",
  "category": "decision",
  "duplicate": false,
  "message": "Memory stored [decision]"
}
```

### Python example

```python
def store(text: str, category: str = "other", importance: float = 0.5,
          metadata: dict | None = None, share_with: list[str] | None = None):
    payload = {
        "text": text,
        "category": category,
        "importance": importance,
        "metadata": metadata or {},
        "collection": "agent-memory",
    }
    if share_with:
        payload["share_with"] = list(share_with)
    with httpx.Client(timeout=4.0) as http:
        resp = http.post(
            f"{API}/v1/store",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
```

### TypeScript example

```ts
export async function store(
  text: string,
  opts: {
    category?: string;
    importance?: number;
    metadata?: Record<string, unknown>;
    share_with?: string[];
  } = {},
) {
  const body: Record<string, unknown> = {
    text,
    category: opts.category ?? "other",
    importance: opts.importance ?? 0.5,
    metadata: opts.metadata ?? {},
    collection: "agent-memory",
  };
  if (opts.share_with?.length) body.share_with = opts.share_with;
  const res = await fetch(`${API}/v1/store`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`store failed: ${res.status}`);
  return res.json();
}
```

---

## Wiring hive sharing (Wave 3)

The `/v1/hives` endpoints are the REST surface the bridge CLI
wraps. Same shapes, no bridge required.

### List hives

```bash
curl -sS https://api.engrammemory.ai/v1/hives \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1"
```

Returns:

```json
{
  "hives": [
    {
      "id": "<uuid>",
      "name": "my-hive",
      "slug": "my-hive",
      "owner_user_id": "<uuid>",
      "role": "owner",
      "member_count": 3,
      "created_at": "..."
    }
  ]
}
```

### Create a hive

```bash
curl -sS https://api.engrammemory.ai/v1/hives \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-hive", "slug": "my-hive"}'
```

Returns the created hive row. You become owner + first member in
the same request — the cloud does the hive row insert and the
owner membership insert in one transaction and rolls back both on
failure.

### Add a member

```bash
curl -sS https://api.engrammemory.ai/v1/hives/<hive_uuid>/members \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<user_uuid>", "role": "member"}'
```

Caller must be owner or admin. `role` is `member` or `admin` —
`owner` is reserved for the hive creator and can't be assigned
through this endpoint.

### Push to a hive

Pass `share_with` on `POST /v1/store`:

```bash
curl -sS https://api.engrammemory.ai/v1/store \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "shipped feature X",
    "category": "decision",
    "importance": 0.6,
    "share_with": ["hive:<hive_uuid>"]
  }'
```

Each `share_with` entry has the form `hive:<hive_uuid>`. The
cloud validates that you're a member of every listed hive before
writing — any hive you aren't in returns 403 and the whole store
call fails (the cloud writes personal + hive fan-out together to
avoid partial state).

### Pull from a hive

Pass `scope` on `POST /v1/search`:

```bash
curl -sS https://api.engrammemory.ai/v1/search \
  -H "Authorization: Bearer $ENGRAM_API_KEY" \
  -H "X-API-Version: 1" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "retry strategy",
    "top_k": 5,
    "scope": "hive:<hive_uuid>"
  }'
```

`scope` is `"personal"` (default) or `"hive:<hive_uuid>"`.
Unauthorized hive scopes return 403.

---

## Composing the two paths

A typical non-MCP agent flow looks like this:

1. **On task start** → `POST /v1/search` with a summary of the
   incoming task, maybe scoped to a hive. Include the returned
   memories as system-prompt context.
2. **On meaningful event** → `POST /v1/store` with a concise
   description (one sentence), a category, and metadata the read
   side will filter on (`project_id`, `branch`, `source`, etc.).
3. **On hive handoff** → include `share_with` on the store call
   so the memory reaches teammates' pull scopes.

---

## Troubleshooting

1. **Config file exists?** (optional — only if you're also using
   the bridge CLI alongside your REST agent)
   `test -f ~/.engram/config.yaml && echo ok || echo missing`
2. **`api_key` set?** On the REST path, the key lives in an env
   var your agent reads. Must start with `eng_live_`.
3. **`enabled: true`?** (bridge only; REST calls don't care)
4. **Cloud reachable?**
   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' \
     https://api.engrammemory.ai/health
   ```
   Must print `200`.
5. **Recent errors?** If you're running alongside the bridge,
   `tail -50 ~/.engram/bridge.log`. For REST-only agents, log
   the `resp.status_code` and `resp.text()` on every failure in
   your own client.

REST-specific checks:

- **401 on every call** → your API key is wrong or expired.
  Rotate it on the Engram dashboard and reload `ENGRAM_API_KEY`.
- **403 on a hive call** → you're not a member of the listed
  hive. Call `GET /v1/hives` to see what you do have access to.
- **422 on store** → `text` is missing or empty. The cloud
  requires a non-empty `text` field even when `content` would
  work on older versions.
- **timeouts** → every example above uses a 4-second timeout to
  match the bridge's default. For batch store jobs, bump it to
  10-30 seconds; the embedding + dedup + Qdrant write path is
  usually sub-second but can spike on cold engines.
