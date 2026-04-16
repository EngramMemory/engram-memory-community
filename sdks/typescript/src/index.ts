/**
 * Public entry point for @engram/sdk.
 *
 * The SDK exports the client, every error class, and all
 * request/response types. Types are re-exported with `export type`
 * so bundlers can tree-shake them away in production builds.
 */

export { EngramClient } from "./client.js";
export type { EngramClientOptions } from "./client.js";

export {
  EngramAPIError,
  EngramAuthError,
  EngramConnectionError,
  EngramError,
  EngramRateLimitError,
} from "./errors.js";

export type {
  AddHiveMemberOptions,
  AddHiveMemberResponse,
  CreateTeamOptions,
  FeedbackOptions,
  FeedbackRequestBody,
  FeedbackResponse,
  ForgetRequestBody,
  ForgetResponse,
  HealthResponse,
  ListTeamsResponse,
  RemoveHiveMemberResponse,
  SearchOptions,
  SearchRequestBody,
  SearchResponse,
  SearchResult,
  StoreOptions,
  StoreRequestBody,
  StoreResponse,
  HiveResponse,
} from "./models.js";
