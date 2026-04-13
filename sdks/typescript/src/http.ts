/**
 * Fetch wrapper with retry, auth injection, and error classification.
 *
 * Design constraints:
 *   1. Zero runtime deps — `fetch` must be whatever the runtime
 *      provides (Node 18+, browser, Workers, Deno, Bun).
 *   2. Injectable `fetch` so Cloudflare Workers / tests / MSW can
 *      substitute their own implementation without monkey-patching
 *      globals.
 *   3. Retry is bounded and only retries idempotent failures. POST
 *      requests that landed server-side (got any status) are NOT
 *      retried on 5xx by default — the caller's memory might already
 *      be stored and a retry would write a duplicate.
 *
 * The retry policy:
 *   - Network errors (no response received) → retry with backoff
 *   - 429 with Retry-After → retry after that delay, up to maxRetries
 *   - 408 / 503 / 504 → retry with backoff (cheap transients)
 *   - Everything else → raise classified error
 *
 * We intentionally do NOT retry on 500 for POSTs. An HTTP 500 from
 * /v1/store after the engine accepted the write is a real failure
 * mode (we've seen it from the webhook fan-out path in api.py
 * L2509-L2529), and retrying creates ghost duplicates.
 */

import {
  EngramAPIError,
  EngramAuthError,
  EngramConnectionError,
  EngramRateLimitError,
} from "./errors.js";

export type FetchLike = typeof fetch;

export interface HttpClientOptions {
  apiKey: string;
  baseUrl: string;
  timeout: number;
  maxRetries: number;
  retryBackoff: number;
  fetchImpl: FetchLike;
}

export interface RequestOptions {
  method: "GET" | "POST" | "DELETE";
  path: string;
  body?: unknown;
  /**
   * If true, this request is safe to retry on 5xx. Set for GET and
   * for POSTs we know are server-side idempotent (e.g. /v1/feedback,
   * which is an upsert of boost/penalty counts keyed on selected_ids).
   * Default: false.
   */
  retryOn5xx?: boolean;
}

/**
 * Thin HTTP layer. Holds credentials, applies them on every request,
 * classifies errors by status, retries transient failures.
 */
export class HttpClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeout: number;
  private readonly maxRetries: number;
  private readonly retryBackoff: number;
  private readonly fetchImpl: FetchLike;

  constructor(opts: HttpClientOptions) {
    this.apiKey = opts.apiKey;
    // Strip trailing slash so path joining is unambiguous. Users who
    // pass `https://api.engrammemory.ai/` get the same behavior as
    // users who pass `https://api.engrammemory.ai`.
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.timeout = opts.timeout;
    this.maxRetries = opts.maxRetries;
    this.retryBackoff = opts.retryBackoff;
    this.fetchImpl = opts.fetchImpl;
  }

  async request<T>(opts: RequestOptions): Promise<T> {
    const url = `${this.baseUrl}${opts.path}`;
    let attempt = 0;
    let lastErr: unknown;

    while (attempt <= this.maxRetries) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeout);

      try {
        const init: RequestInit = {
          method: opts.method,
          headers: this.buildHeaders(opts.body !== undefined),
          signal: controller.signal,
        };
        if (opts.body !== undefined) {
          init.body = JSON.stringify(opts.body);
        }

        const res = await this.fetchImpl(url, init);
        clearTimeout(timer);

        if (res.ok) {
          // 204 No Content or empty body → return null-typed
          if (res.status === 204) {
            return undefined as unknown as T;
          }
          const text = await res.text();
          if (!text) {
            return undefined as unknown as T;
          }
          return JSON.parse(text) as T;
        }

        // Non-2xx: classify, decide whether to retry
        const bodyText = await res.text().catch(() => "");
        const parsed = safeJsonParse(bodyText);

        if (res.status === 401) {
          throw new EngramAuthError(
            extractMessage(parsed) ?? "Authentication failed",
            parsed ?? bodyText,
          );
        }

        if (res.status === 429) {
          const retryAfter = parseRetryAfter(res.headers.get("retry-after"));
          // Only retry 429 if we actually have a Retry-After hint
          // and we have attempts left. Engram's quota is monthly and
          // the server does not send Retry-After on quota errors
          // (api.py L1544-L1561), so this almost always throws.
          if (retryAfter !== null && attempt < this.maxRetries) {
            await sleep(retryAfter * 1000);
            attempt += 1;
            continue;
          }
          throw new EngramRateLimitError(
            extractMessage(parsed) ?? "Rate limit exceeded",
            retryAfter,
            parsed ?? bodyText,
          );
        }

        // Transient server errors — retry if caller opted in
        if (
          opts.retryOn5xx &&
          (res.status === 408 ||
            res.status === 502 ||
            res.status === 503 ||
            res.status === 504) &&
          attempt < this.maxRetries
        ) {
          await sleep(this.retryBackoff * Math.pow(2, attempt));
          attempt += 1;
          continue;
        }

        throw new EngramAPIError(
          extractMessage(parsed) ?? `HTTP ${res.status}`,
          res.status,
          parsed ?? bodyText,
        );
      } catch (err) {
        clearTimeout(timer);

        // Rethrow classified errors immediately
        if (
          err instanceof EngramAuthError ||
          err instanceof EngramAPIError ||
          err instanceof EngramRateLimitError
        ) {
          throw err;
        }

        // Network / abort / timeout — retry if we have attempts left
        lastErr = err;
        if (attempt < this.maxRetries) {
          await sleep(this.retryBackoff * Math.pow(2, attempt));
          attempt += 1;
          continue;
        }

        // Out of attempts — wrap and throw
        throw new EngramConnectionError(
          `Failed to reach ${url}: ${describeError(err)}`,
          err,
        );
      }
    }

    // Unreachable in practice — loop exits via return or throw above
    throw new EngramConnectionError(
      `Exhausted ${this.maxRetries} retries for ${url}`,
      lastErr,
    );
  }

  private buildHeaders(hasBody: boolean): Record<string, string> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: "application/json",
      "User-Agent": "engram-sdk-ts/0.1.0",
    };
    if (hasBody) {
      headers["Content-Type"] = "application/json";
    }
    return headers;
  }
}

function safeJsonParse(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * Pull a human-readable error string from a decoded JSON body.
 *
 * Engram's error envelopes vary: sometimes `{detail: "…"}`, sometimes
 * `{detail: {error, message, code}}`, sometimes `{error, message}`.
 * We probe in order and fall back to null if nothing matches, letting
 * the caller use the HTTP status as the message.
 */
function extractMessage(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;

  if (typeof b.detail === "string") return b.detail;
  if (b.detail && typeof b.detail === "object") {
    const d = b.detail as Record<string, unknown>;
    if (typeof d.message === "string") return d.message;
    if (typeof d.error === "string") return d.error;
  }
  if (typeof b.message === "string") return b.message;
  if (typeof b.error === "string") return b.error;
  return null;
}

/**
 * Parse a Retry-After header. RFC 7231 allows either an integer
 * seconds value or an HTTP-date. We support both.
 */
function parseRetryAfter(header: string | null): number | null {
  if (!header) return null;
  const asInt = Number.parseInt(header, 10);
  if (!Number.isNaN(asInt) && asInt >= 0) return asInt;
  const asDate = Date.parse(header);
  if (!Number.isNaN(asDate)) {
    const diff = Math.ceil((asDate - Date.now()) / 1000);
    return diff > 0 ? diff : 0;
  }
  return null;
}

function describeError(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return String(err);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
