/**
 * EngramClient — the public face of the SDK.
 *
 * Everything below is a typed method that hits one endpoint in
 * engram-cloud-api/api.py. The translation from camelCase public
 * options to snake_case wire format is explicit on a per-method
 * basis rather than automatic, because some camelCase names (topK →
 * limit) don't map by simple case conversion.
 */

import {
  EngramAPIError,
  EngramAuthError,
  EngramConnectionError,
  EngramError,
  EngramRateLimitError,
} from "./errors.js";
import { FetchLike, HttpClient } from "./http.js";
import type {
  CreateTeamOptions,
  FeedbackOptions,
  FeedbackResponse,
  ForgetResponse,
  GrantHiveAccessOptions,
  GrantHiveAccessResponse,
  HealthResponse,
  HiveGrant,
  ListHiveGrantsResponse,
  ListTeamsResponse,
  RevokeHiveAccessResponse,
  SearchOptions,
  SearchResponse,
  StoreOptions,
  StoreResponse,
  HiveResponse,
} from "./models.js";

export interface EngramClientOptions {
  /**
   * Required. No environment fallback — if a caller wants to read
   * from `process.env.ENGRAM_API_KEY`, they do it themselves before
   * constructing the client. This keeps the constructor pure and
   * testable, and avoids surprising behavior in edge runtimes where
   * `process.env` doesn't exist.
   */
  apiKey: string;

  /** Default: https://api.engrammemory.ai */
  baseUrl?: string;

  /** Request timeout in milliseconds. Default: 30000. */
  timeout?: number;

  /**
   * Max retry attempts for network errors and transient 5xx. Default: 3.
   * Note: POST endpoints that are not provably idempotent (store,
   * forget, create-hive, add/remove member) do NOT retry on 5xx
   * regardless of this value — see http.ts for the rationale.
   */
  maxRetries?: number;

  /**
   * Base backoff in ms between retries. The actual delay is
   * `retryBackoff * 2^attempt` (exponential). Default: 500.
   */
  retryBackoff?: number;

  /**
   * Inject a custom fetch implementation. Useful for Cloudflare
   * Workers (`globalThis.fetch`), Node <18 with `undici` installed,
   * or test environments with `msw`. Defaults to `globalThis.fetch`.
   */
  fetch?: FetchLike;
}

const DEFAULT_BASE_URL = "https://api.engrammemory.ai";
const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_BACKOFF_MS = 500;

export class EngramClient {
  private readonly http: HttpClient;

  constructor(opts: EngramClientOptions) {
    if (!opts.apiKey || typeof opts.apiKey !== "string") {
      throw new EngramError(
        "EngramClient requires an apiKey. Pass { apiKey: 'pr_live_...' }.",
      );
    }

    const fetchImpl =
      opts.fetch ??
      (typeof globalThis !== "undefined" && typeof globalThis.fetch === "function"
        ? globalThis.fetch.bind(globalThis)
        : undefined);

    if (!fetchImpl) {
      throw new EngramError(
        "No fetch implementation available. Pass { fetch } explicitly or run on Node 18+, modern browsers, Workers, Deno, or Bun.",
      );
    }

    this.http = new HttpClient({
      apiKey: opts.apiKey,
      baseUrl: opts.baseUrl ?? DEFAULT_BASE_URL,
      timeout: opts.timeout ?? DEFAULT_TIMEOUT_MS,
      maxRetries: opts.maxRetries ?? DEFAULT_MAX_RETRIES,
      retryBackoff: opts.retryBackoff ?? DEFAULT_RETRY_BACKOFF_MS,
      fetchImpl,
    });
  }

  // ─── Memory ────────────────────────────────────────────────────────

  /**
   * Store a memory. Hits `POST /v1/store`.
   */
  async store(opts: StoreOptions): Promise<StoreResponse> {
    if (!opts.text) {
      throw new EngramError("store() requires { text }.");
    }
    const body: Record<string, unknown> = { text: opts.text };
    if (opts.category !== undefined) body.category = opts.category;
    if (opts.importance !== undefined) body.importance = opts.importance;
    if (opts.metadata !== undefined) body.metadata = opts.metadata;
    if (opts.collection !== undefined) body.collection = opts.collection;

    return this.http.request<StoreResponse>({
      method: "POST",
      path: "/v1/store",
      body,
      retryOn5xx: false,
    });
  }

  /**
   * Semantic search. Hits `POST /v1/search` (api.py L2542).
   *
   * `topK` maps to the wire-level `limit` field (default 5). `scope`
   * accepts `"personal"` or `"hive:<uuid>"` — Wave 3 addition, see
   * api.py L2574-L2587 for the routing logic.
   */
  async search(opts: SearchOptions): Promise<SearchResponse> {
    if (!opts.query) {
      throw new EngramError("search() requires { query }.");
    }
    const body: Record<string, unknown> = { query: opts.query };
    if (opts.queries !== undefined) body.queries = opts.queries;
    if (opts.topK !== undefined) body.limit = opts.topK;
    if (opts.scope !== undefined) body.scope = opts.scope;
    if (opts.category !== undefined) body.category = opts.category;
    if (opts.minScore !== undefined) body.min_score = opts.minScore;
    if (opts.minImportance !== undefined)
      body.min_importance = opts.minImportance;
    if (opts.collection !== undefined) body.collection = opts.collection;

    return this.http.request<SearchResponse>({
      method: "POST",
      path: "/v1/search",
      body,
      // Read-only semantically — embed + search has no side effects
      // beyond the specificity counter update, which is idempotent.
      retryOn5xx: true,
    });
  }

  /**
   * Delete a memory by ID. Hits `POST /v1/forget` (api.py L2748).
   *
   * The endpoint also supports forget-by-query, but we expose only
   * the ID form on the public surface — forget-by-query has a subtle
   * gotcha (it deletes the single top search result) that should be
   * opt-in via an explicit second method if we decide we want it.
   */
  async forget(memoryId: string): Promise<ForgetResponse> {
    if (!memoryId) {
      throw new EngramError("forget() requires a memoryId.");
    }
    return this.http.request<ForgetResponse>({
      method: "POST",
      path: "/v1/forget",
      body: { memory_id: memoryId },
      retryOn5xx: false,
    });
  }

  /**
   * Record rerank feedback. Hits `POST /v1/feedback` (api.py L2704).
   *
   * Idempotent upserts of hot-tier boosts and PREFERRED_OVER graph
   * edges — safe to retry.
   */
  async feedback(opts: FeedbackOptions): Promise<FeedbackResponse> {
    if (!opts.query) {
      throw new EngramError("feedback() requires { query }.");
    }
    if (!Array.isArray(opts.selectedIds)) {
      throw new EngramError("feedback() requires { selectedIds: string[] }.");
    }
    return this.http.request<FeedbackResponse>({
      method: "POST",
      path: "/v1/feedback",
      body: {
        query: opts.query,
        selected_ids: opts.selectedIds,
        rejected_ids: opts.rejectedIds ?? [],
      },
      retryOn5xx: true,
    });
  }

  // ─── Hives (Wave 3) ────────────────────────────────────────────────

  /**
   * Create a hive. Hits `POST /v1/hives` (api.py L2871).
   *
   * Caller becomes owner in the same transaction that creates the
   * hive row. Slug must be 3-48 chars, lowercase alphanumerics and
   * hyphens (api.py L2843, L2846-L2857).
   */
  async createTeam(opts: CreateTeamOptions): Promise<HiveResponse> {
    if (!opts.name || !opts.slug) {
      throw new EngramError("createTeam() requires { name, slug }.");
    }
    return this.http.request<HiveResponse>({
      method: "POST",
      path: "/v1/hives",
      body: { name: opts.name, slug: opts.slug },
      retryOn5xx: false,
    });
  }

  /**
   * List hives the caller is a member of. Hits `GET /v1/hives`
   * (api.py L2961). Unwraps the server's `{hives: [...]}` envelope
   * (api.py L3011) and returns the array directly.
   */
  async listTeams(): Promise<HiveResponse[]> {
    const res = await this.http.request<ListTeamsResponse>({
      method: "GET",
      path: "/v1/hives",
      retryOn5xx: true,
    });
    return res.hives ?? [];
  }

  /**
   * Grant an API key access to a hive.
   * Hits `POST /v1/hives/{hive_id}/grants`.
   */
  async grantHiveAccess(
    hiveId: string,
    opts: GrantHiveAccessOptions,
  ): Promise<GrantHiveAccessResponse> {
    if (!hiveId) {
      throw new EngramError("grantHiveAccess() requires a hiveId.");
    }
    if (!opts.keyPrefix) {
      throw new EngramError("grantHiveAccess() requires { keyPrefix }.");
    }
    const body: Record<string, unknown> = { key_prefix: opts.keyPrefix };
    if (opts.permission !== undefined) body.permission = opts.permission;

    return this.http.request<GrantHiveAccessResponse>({
      method: "POST",
      path: `/v1/hives/${encodeURIComponent(hiveId)}/grants`,
      body,
      retryOn5xx: false,
    });
  }

  /**
   * Revoke an API key's access to a hive.
   * Hits `DELETE /v1/hives/{hive_id}/grants/{key_prefix}`.
   */
  async revokeHiveAccess(
    hiveId: string,
    keyPrefix: string,
  ): Promise<RevokeHiveAccessResponse> {
    if (!hiveId || !keyPrefix) {
      throw new EngramError(
        "revokeHiveAccess() requires (hiveId, keyPrefix).",
      );
    }
    return this.http.request<RevokeHiveAccessResponse>({
      method: "DELETE",
      path: `/v1/hives/${encodeURIComponent(hiveId)}/grants/${encodeURIComponent(keyPrefix)}`,
      retryOn5xx: false,
    });
  }

  /**
   * List grants for a hive.
   * Hits `GET /v1/hives/{hive_id}/grants`.
   */
  async listHiveGrants(hiveId: string): Promise<HiveGrant[]> {
    if (!hiveId) {
      throw new EngramError("listHiveGrants() requires a hiveId.");
    }
    const res = await this.http.request<ListHiveGrantsResponse>({
      method: "GET",
      path: `/v1/hives/${encodeURIComponent(hiveId)}/grants`,
      retryOn5xx: true,
    });
    return res.grants ?? [];
  }

  // ─── System ────────────────────────────────────────────────────────

  /**
   * Health check. Hits `GET /v1/health` (api.py L3296).
   *
   * Requires auth — the API's health check is per-user because it
   * also verifies the caller's Qdrant instance is reachable, not
   * just the API process.
   */
  async health(): Promise<HealthResponse> {
    return this.http.request<HealthResponse>({
      method: "GET",
      path: "/v1/health",
      retryOn5xx: true,
    });
  }
}

// Re-export error classes so callers can `import { EngramClient,
// EngramAuthError } from "@engram/sdk"` without a second import line.
export {
  EngramAPIError,
  EngramAuthError,
  EngramConnectionError,
  EngramError,
  EngramRateLimitError,
};
