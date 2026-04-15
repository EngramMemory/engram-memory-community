/**
 * Error hierarchy for the Engram SDK.
 *
 * Callers discriminate on class, not on status. A 429 from the rate
 * limiter is not the same kind of problem as a 500 from a downstream
 * Qdrant blip, and the SDK surfaces that distinction at the type level
 * so retry loops and alerting don't have to parse message strings.
 *
 * Error bodies from the API come back as JSON with a loose shape —
 * sometimes `{error, message, code}`, sometimes `{detail: "…"}`,
 * sometimes `{detail: {error, message, code}}`. We keep the raw body
 * around on `EngramAPIError.body` so callers can pull whatever field
 * they need without us committing to one envelope.
 */

export class EngramError extends Error {
  public readonly name: string = "EngramError";

  constructor(message: string) {
    super(message);
    // Preserve the prototype chain across transpile targets that
    // otherwise break `instanceof` (ES5 target, Babel, etc.).
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * 401 — API key missing, invalid, or revoked.
 *
 * The Engram API returns 401 for any auth failure; we don't try to
 * guess whether it's an expired key vs a typo. Caller decides whether
 * to prompt for a new key or fail the whole process.
 */
export class EngramAuthError extends EngramError {
  public readonly name = "EngramAuthError";
  public readonly status = 401;
  public readonly body: unknown;

  constructor(message: string, body?: unknown) {
    super(message);
    this.body = body;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * 429 — monthly quota exceeded on a billable resource.
 *
 * `retryAfter` is seconds until the quota resets, extracted from the
 * `Retry-After` header if present. When the server doesn't send one
 * (Engram's quota is monthly, so an immediate retry is pointless),
 * this defaults to `null` and callers should fall back to their own
 * backoff policy rather than spinning.
 */
export class EngramRateLimitError extends EngramError {
  public readonly name = "EngramRateLimitError";
  public readonly status = 429;
  public readonly retryAfter: number | null;
  public readonly body: unknown;

  constructor(message: string, retryAfter: number | null, body?: unknown) {
    super(message);
    this.retryAfter = retryAfter;
    this.body = body;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Generic 4xx/5xx error wrapper.
 *
 * `body` is the decoded JSON body when the response was JSON, else
 * the raw text. We do not try to normalize — the Engram error shapes
 * vary enough between endpoints that normalizing here would destroy
 * information callers might need.
 */
export class EngramAPIError extends EngramError {
  public readonly name = "EngramAPIError";
  public readonly status: number;
  public readonly body: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Network / fetch-level failure.
 *
 * Used for DNS failures, connection refused, TLS errors, aborts,
 * and anything else that prevents us from getting a status code at
 * all. Retry loop in `http.ts` retries this before giving up.
 */
export class EngramConnectionError extends EngramError {
  public readonly name = "EngramConnectionError";
  public readonly cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.cause = cause;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
