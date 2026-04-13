/**
 * TypeScript counterparts for the Pydantic request/response models
 * defined in engram-cloud-api/api.py. Field names mirror the wire
 * format exactly (snake_case) so a JSON.parse on the raw response
 * gives you a valid instance without a translation layer.
 *
 * Source of truth is api.py; the line numbers in comments reference
 * that file as of the 2026-04 shape so a future API change that
 * diverges from these types is easy to spot in review.
 */

// ─── Memory primitives ───────────────────────────────────────────────

/**
 * StoreRequest body for `POST /v1/store`.
 *
 * Mirrors `class StoreRequest` in api.py L602-L611. Required fields:
 *   text (string)
 * Optional fields default server-side:
 *   category → "other"
 *   importance → 0.5
 *   metadata → null
 *   collection → "agent-memory"
 *   share_with → null
 *
 * `shareWith` is the camelCase-facing name; we translate it to
 * `share_with` at the wire layer in client.ts. Wave 3 added this —
 * entries take the form `"team:<uuid>"` and any team the caller isn't
 * a member of returns 403 (api.py L2457-L2467).
 */
export interface StoreRequestBody {
  text: string;
  category?: string;
  importance?: number;
  metadata?: Record<string, unknown>;
  collection?: string;
  share_with?: string[];
}

/** `class StoreResponse` — api.py L614-L619. */
export interface StoreResponse {
  id: string;
  status: string;
  category: string;
  duplicate: boolean;
  message: string;
}

/**
 * SearchRequest body for `POST /v1/search`.
 *
 * Mirrors `class SearchRequest` in api.py L622-L644.
 *
 * `scope` (Wave 3, L637-L644) accepts:
 *   "personal" (default) — caller's own collection
 *   "team:<uuid>"        — team collection, requires membership
 *
 * `queries` is an optional list of up to 3 additional query variants
 * for RRF-merged multi-query search (L623-L631, L2596 cap at 4 total).
 */
export interface SearchRequestBody {
  query: string;
  queries?: string[];
  limit?: number;
  category?: string;
  min_score?: number;
  min_importance?: number;
  collection?: string;
  scope?: string;
}

/** Single result inside SearchResponse — api.py L666-L675. */
export interface SearchResult {
  id: string;
  text: string;
  category: string;
  importance: number;
  score: number;
  timestamp: string;
  confidence?: string | null;
  match_context?: string | null;
  tier?: string | null;
}

/** `class SearchResponse` — api.py L678-L680. */
export interface SearchResponse {
  results: SearchResult[];
  query_tokens: number;
}

/** `class ForgetRequest` — api.py L683-L686. */
export interface ForgetRequestBody {
  memory_id?: string;
  query?: string;
  collection?: string;
}

/**
 * /v1/forget return envelope. The endpoint returns a dict literal
 * (api.py L2784, L2828-L2832, L2794), not a declared Pydantic model,
 * so the shape is: always `status` + `id`, sometimes `text` on
 * query-match, `{status:"not_found", message}` on miss.
 */
export interface ForgetResponse {
  status: string;
  id?: string;
  text?: string;
  message?: string;
}

/**
 * `class FeedbackRequest` — api.py L2698-L2701.
 *
 * Note the server-side field is `selected_ids` / `rejected_ids`. The
 * public SDK surface uses camelCase (`selectedIds` / `rejectedIds`)
 * and client.ts handles the translation.
 */
export interface FeedbackRequestBody {
  query: string;
  selected_ids: string[];
  rejected_ids?: string[];
}

/** Return envelope from /v1/feedback — api.py L2738-L2743. */
export interface FeedbackResponse {
  success: boolean;
  boosted: number;
  penalized: number;
  edges_added: number;
}

// ─── Teams (Wave 3) ──────────────────────────────────────────────────

/** `class CreateTeamRequest` — api.py L647-L649. */
export interface CreateTeamRequestBody {
  name: string;
  slug: string;
}

/** `class AddMemberRequest` — api.py L652-L654. Default role="member". */
export interface AddMemberRequestBody {
  user_id: string;
  role?: string;
}

/**
 * `class TeamResponse` — api.py L657-L663.
 *
 * `created_at` is serialized as an ISO-8601 datetime string on the
 * wire (FastAPI's default for `datetime`), so we type it as `string`
 * rather than `Date` and leave parsing to the caller.
 */
export interface TeamResponse {
  id: string;
  name: string;
  slug: string;
  owner_user_id: string;
  created_at: string;
  member_count: number;
  /**
   * Only present on list responses — comes from the team_memberships
   * join in api.py L2982-L3007 (`list_teams`). Not on create or member
   * mutation responses.
   */
  role?: string;
}

/**
 * Envelope around GET /v1/teams. The endpoint returns
 * `{"teams": [...]}` (api.py L3011), not a bare array, so we expose
 * the wrapper here and unwrap in the client.
 */
export interface ListTeamsResponse {
  teams: TeamResponse[];
}

/**
 * Return envelope from POST /v1/teams/{id}/members — api.py L3079-L3083.
 * `joined_at` is ISO-8601 or null.
 */
export interface AddTeamMemberResponse {
  team_id: string;
  user_id: string;
  role: string;
  joined_at: string | null;
}

/**
 * Return envelope from DELETE /v1/teams/{id}/members/{user_id}
 * — api.py L3152.
 */
export interface RemoveTeamMemberResponse {
  team_id: string;
  user_id: string;
  removed: boolean;
}

// ─── System ──────────────────────────────────────────────────────────

/** `class HealthStatus` — api.py L737-L744. */
export interface HealthResponse {
  api: string;
  embedding: string;
  qdrant: string;
  qdrant_url: string;
  uptime_seconds: number;
  version: string;
  environment: string;
}

// ─── Client-facing option types ──────────────────────────────────────

/**
 * Public camelCase shape for `EngramClient.store()`. The client
 * translates these to the snake_case wire format.
 */
export interface StoreOptions {
  text: string;
  category?: string;
  importance?: number;
  metadata?: Record<string, unknown>;
  collection?: string;
  shareWith?: string[];
}

export interface SearchOptions {
  query: string;
  queries?: string[];
  topK?: number;
  scope?: string;
  category?: string;
  minScore?: number;
  minImportance?: number;
  collection?: string;
}

export interface FeedbackOptions {
  query: string;
  selectedIds: string[];
  rejectedIds?: string[];
}

export interface CreateTeamOptions {
  name: string;
  slug: string;
}

export interface AddTeamMemberOptions {
  userId: string;
  role?: string;
}
