"""httpx wrapper for the Engram cloud API.

Kept deliberately thin — this module owns nothing but HTTP I/O and the
tiny typed shapes we need. All higher-level logic (disabled-detection,
silent failure, logging) lives in ``pull.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from .config import BridgeConfig


API_VERSION = "1"
DEFAULT_TIMEOUT = 4.0
HEALTH_TIMEOUT = 2.0


@dataclass
class SearchResult:
    """One hit returned by ``POST /v1/search``."""

    id: str
    content: str
    score: float
    metadata: Dict[str, Any]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "SearchResult":
        return cls(
            id=str(raw.get("id", "")),
            content=str(raw.get("content", "")),
            score=float(raw.get("score", 0.0) or 0.0),
            metadata=raw.get("metadata") or {},
        )


class EngramClient:
    """Minimal client for the cloud API. Not a context manager — the
    bridge always builds, uses, and drops the client within a single CLI
    invocation."""

    def __init__(self, config: BridgeConfig, timeout: float = DEFAULT_TIMEOUT):
        self._config = config
        self._timeout = timeout

    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer {}".format(self._config.api_key),
            "X-API-Version": API_VERSION,
            "User-Agent": "engram-bridge/0.1",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return "{}/{}".format(self._config.api_base.rstrip("/"), path.lstrip("/"))

    # ------------------------------------------------------------------
    def health(self, timeout: Optional[float] = None) -> bool:
        """Cheap reachability probe. Returns True only on HTTP 2xx within
        ``timeout`` seconds. Any other outcome (timeout, 4xx, 5xx,
        connection error) returns False. Never raises.

        Uses the public ``/health`` endpoint (no auth) so that "is the
        API reachable?" is cleanly separated from "is my api_key valid?"
        — we don't want a rotated key to look like an outage. The
        authed ``/v1/health`` is available but requires a valid Bearer
        token; we deliberately avoid it for reachability probes.
        """
        t = timeout if timeout is not None else HEALTH_TIMEOUT
        try:
            with httpx.Client(timeout=t) as http:
                resp = http.get(self._url("/health"))
                return 200 <= resp.status_code < 300
        except (httpx.HTTPError, OSError):
            return False

    def store_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        classification: Optional[str] = None,
        collection: str = "agent-memory",
        importance: float = 0.5,
        share_with: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """POST /v1/store. Returns the decoded response dict on success,
        ``None`` on any failure. Never raises.

        The cloud ``StoreRequest`` model uses ``text`` for the body and
        ``category`` for classification, so we map here once and keep
        the caller's vocabulary (``content`` / ``classification``)
        closer to how we talk about events in the bridge layer.

        ``share_with`` forwards the Wave 3 team fanout list. Each entry
        should be a ``"team:<team_id>"`` scope string; the cloud
        validates membership and returns 403 for any team the caller
        isn't in.
        """
        payload: Dict[str, Any] = {
            "text": content,
            "category": classification or "other",
            "importance": float(importance),
            "metadata": metadata or {},
            "collection": collection,
        }
        if share_with:
            payload["share_with"] = list(share_with)
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.post(
                    self._url("/v1/store"),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
        return body if isinstance(body, dict) else None

    def search(
        self,
        query: str,
        top_k: int,
        scope: str = "personal",
    ) -> List[SearchResult]:
        """POST /v1/search. Returns [] on any failure. Never raises.

        Callers that need to distinguish "0 results" from "API error"
        should use ``search_raw`` instead. ``scope`` passes through to
        the cloud's Wave 3 scope param (``"personal"`` or
        ``"team:<team_id>"``).
        """
        try:
            return self.search_raw(query, top_k, scope=scope)
        except (httpx.HTTPError, OSError, ValueError):
            return []

    def search_raw(
        self,
        query: str,
        top_k: int,
        scope: str = "personal",
    ) -> List[SearchResult]:
        """Like ``search`` but raises on error. Used by tests and by
        ``pull.py`` which wants to log the specific failure."""
        payload: Dict[str, Any] = {
            "query": query,
            "top_k": int(top_k),
            "scope": scope or "personal",
        }
        with httpx.Client(timeout=self._timeout) as http:
            resp = http.post(
                self._url("/v1/search"),
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        if not isinstance(body, dict):
            raise ValueError("search response is not a JSON object")
        results = body.get("results") or []
        if not isinstance(results, list):
            raise ValueError("search response 'results' is not a list")
        out: List[SearchResult] = []
        for item in results:
            if isinstance(item, dict):
                out.append(SearchResult.from_dict(item))
        return out

    # ------------------------------------------------------------------
    # Wave 3 — teams
    # ------------------------------------------------------------------

    def list_teams(self) -> Optional[List[Dict[str, Any]]]:
        """GET /v1/teams. Returns the decoded list, or ``None`` on
        failure. Never raises."""
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.get(
                    self._url("/v1/teams"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
        if not isinstance(body, dict):
            return None
        teams = body.get("teams")
        if not isinstance(teams, list):
            return None
        return [t for t in teams if isinstance(t, dict)]

    def create_team(self, name: str, slug: str) -> Optional[Dict[str, Any]]:
        """POST /v1/teams. Returns the decoded team dict, or ``None``
        on failure. Never raises."""
        payload = {"name": name, "slug": slug}
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.post(
                    self._url("/v1/teams"),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
        return body if isinstance(body, dict) else None

    def add_team_member(
        self,
        team_id: str,
        user_id: str,
        role: str = "member",
    ) -> Optional[Dict[str, Any]]:
        """POST /v1/teams/{team_id}/members. Returns the decoded
        membership dict, or ``None`` on failure. Never raises."""
        payload = {"user_id": user_id, "role": role}
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.post(
                    self._url("/v1/teams/{}/members".format(team_id)),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
        return body if isinstance(body, dict) else None
