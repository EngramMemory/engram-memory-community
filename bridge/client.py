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
        ``"hive:<hive_id>"``).
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
    # Wave 3 — hives
    # ------------------------------------------------------------------

    def list_hives(self) -> Optional[List[Dict[str, Any]]]:
        """GET /v1/hives. Returns the decoded list, or ``None`` on
        failure. Never raises."""
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.get(
                    self._url("/v1/hives"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
        if not isinstance(body, dict):
            return None
        hives = body.get("hives")
        if not isinstance(hives, list):
            return None
        return [t for t in hives if isinstance(t, dict)]

    def create_hive(self, name: str, slug: str) -> Optional[Dict[str, Any]]:
        """POST /v1/hives. Returns the decoded hive dict, or ``None``
        on failure. Never raises."""
        payload = {"name": name, "slug": slug}
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.post(
                    self._url("/v1/hives"),
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None
        return body if isinstance(body, dict) else None

    def grant_hive_access(self, hive_id: str, key_prefix: str, permission: str = "readwrite"):
        """POST /v1/hives/{hive_id}/grants"""
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.post(
                    self._url("/v1/hives/{}/grants".format(hive_id)),
                    json={"key_prefix": key_prefix, "permission": permission},
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if resp.status_code >= 400:
                    return None
                return resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None

    def revoke_hive_access(self, hive_id: str, key_prefix: str):
        """DELETE /v1/hives/{hive_id}/grants/{key_prefix}"""
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.delete(
                    self._url("/v1/hives/{}/grants/{}".format(hive_id, key_prefix)),
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if resp.status_code >= 400:
                    return None
                return resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            return None

    def list_hive_grants(self, hive_id: str):
        """GET /v1/hives/{hive_id}/grants"""
        try:
            with httpx.Client(timeout=self._timeout) as http:
                resp = http.get(
                    self._url("/v1/hives/{}/grants".format(hive_id)),
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if resp.status_code >= 400:
                    return None
                body = resp.json()
            grants = body.get("grants")
            if not isinstance(grants, list):
                return None
            return [g for g in grants if isinstance(g, dict)]
        except (httpx.HTTPError, OSError, ValueError):
            return None
