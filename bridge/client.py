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
        connection error) returns False. Never raises."""
        t = timeout if timeout is not None else HEALTH_TIMEOUT
        try:
            with httpx.Client(timeout=t) as http:
                resp = http.get(
                    self._url("/v1/health"),
                    headers=self._headers(),
                )
                return 200 <= resp.status_code < 300
        except (httpx.HTTPError, OSError):
            return False

    def search(self, query: str, top_k: int) -> List[SearchResult]:
        """POST /v1/search. Returns [] on any failure. Never raises.

        Callers that need to distinguish "0 results" from "API error"
        should use ``search_raw`` instead.
        """
        try:
            return self.search_raw(query, top_k)
        except (httpx.HTTPError, OSError, ValueError):
            return []

    def search_raw(self, query: str, top_k: int) -> List[SearchResult]:
        """Like ``search`` but raises on error. Used by tests and by
        ``pull.py`` which wants to log the specific failure."""
        payload = {"query": query, "top_k": int(top_k)}
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
