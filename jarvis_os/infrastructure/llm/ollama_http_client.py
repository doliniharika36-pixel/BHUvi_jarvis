"""Local Ollama HTTP client.

Provides a minimal HTTP wrapper for the Ollama REST API used by
`OllamaProvider`.

Design goals:
- No business logic.
- Supports timeouts.
- Centralizes request/response parsing.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Generator, Iterable, Iterator, Optional


@dataclass(frozen=True)
class OllamaHTTPConfig:
    base_url: str = "http://localhost:11434"
    request_timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.2


class OllamaHTTPClient:
    def __init__(self, config: OllamaHTTPConfig) -> None:
        self._config = config

    def list_models(self) -> Any:
        """Calls GET /api/tags and returns parsed JSON."""
        url = self._config.base_url.rstrip("/") + "/api/tags"
        return self._request_json("GET", url)

    def generate(self, payload: Dict[str, Any], stream: bool = False) -> Any:
        """Calls POST /api/generate.

        If stream=True, returns an iterator of JSON-decoded chunks.
        Otherwise returns parsed JSON.
        """
        url = self._config.base_url.rstrip("/") + "/api/generate"
        if stream:
            return self._request_stream_json(payload, url)
        return self._request_json("POST", url, payload)

    def embeddings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Calls POST /api/embeddings."""
        url = self._config.base_url.rstrip("/") + "/api/embeddings"
        return self._request_json("POST", url, payload)

    def _request_json(self, method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        headers = {"Content-Type": "application/json"}
        data: Optional[bytes] = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        last_exc: Optional[BaseException] = None
        for attempt in range(self._config.max_retries + 1):
            try:
                req = urllib.request.Request(url=url, method=method, headers=headers, data=data)
                with urllib.request.urlopen(req, timeout=self._config.request_timeout_seconds) as resp:
                    body = resp.read()
                    if not body:
                        return {}
                    return json.loads(body.decode("utf-8"))
            except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
                last_exc = e
                if attempt >= self._config.max_retries:
                    raise
                time.sleep(self._config.retry_backoff_seconds * (attempt + 1))
        if last_exc:
            raise last_exc
        return {}

    def _request_stream_json(self, payload: Dict[str, Any], url: str) -> Iterator[Dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8")

        last_exc: Optional[BaseException] = None
        for attempt in range(self._config.max_retries + 1):
            try:
                req = urllib.request.Request(url=url, method="POST", headers=headers, data=data)
                with urllib.request.urlopen(req, timeout=self._config.request_timeout_seconds) as resp:
                    # Ollama streams JSON objects separated by newlines.
                    for raw_line in resp:
                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        yield json.loads(line)
                return
            except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
                last_exc = e
                if attempt >= self._config.max_retries:
                    raise
                time.sleep(self._config.retry_backoff_seconds * (attempt + 1))
        if last_exc:
            raise last_exc

