"""LLM provider interface. xAI Grok is the default; others implement the same `complete_json`."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from logidx.settings import Settings, get_settings


class ProviderError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, schema_name: str, schema: dict[str, Any]) -> LLMResult: ...


class GrokProvider:
    """xAI chat completions API (OpenAI-compatible) with JSON-schema structured output."""

    name = "xai"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        s = settings or get_settings()
        self._key = s.xai_api_key.get_secret_value()
        if not self._key:
            raise ProviderError("XAI_API_KEY is not configured")
        self.model = s.xai_model
        self.base_url = s.xai_base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self._sleep = sleep

    def complete_json(self, system: str, user: str, schema_name: str, schema: dict[str, Any]) -> LLMResult:
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        }
        last_error = "unknown error"
        for attempt in range(3):
            try:
                resp = self.client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers={"Authorization": f"Bearer {self._key}"}
                )
            except httpx.TransportError as exc:
                last_error = f"transport error: {type(exc).__name__}"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage") or {}
                    try:
                        text = data["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, TypeError) as exc:
                        raise ProviderError("unexpected response shape from xAI") from exc
                    return LLMResult(
                        text=text,
                        model=data.get("model", self.model),
                        tokens_in=int(usage.get("prompt_tokens") or 0),
                        tokens_out=int(usage.get("completion_tokens") or 0),
                    )
                if resp.status_code in (401, 403):
                    raise ProviderError(f"xAI rejected the API key (HTTP {resp.status_code})")
                last_error = f"HTTP {resp.status_code}: {_safe_error(resp)}"
                if resp.status_code not in (408, 429) and resp.status_code < 500:
                    raise ProviderError(last_error)
            self._sleep(2**attempt)
        raise ProviderError(last_error)


def _safe_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        msg = body.get("error") if isinstance(body, dict) else body
        return json.dumps(msg)[:300]
    except ValueError:
        return resp.text[:300]


class StaticProvider:
    """Deterministic provider for tests and offline demos: returns whatever `respond` produces."""

    name = "static"

    def __init__(self, respond: Callable[[str, str], str], model: str = "static-test") -> None:
        self.respond = respond
        self.model = model

    def complete_json(self, system: str, user: str, schema_name: str, schema: dict[str, Any]) -> LLMResult:
        text = self.respond(system, user)
        return LLMResult(text=text, model=self.model, tokens_in=len(system + user) // 4, tokens_out=len(text) // 4)


def get_provider(settings: Settings | None = None) -> LLMProvider | None:
    """The configured provider, or None if not configured (AI steps are then skipped and reported)."""
    s = settings or get_settings()
    if s.ai_provider == "grok" and s.xai_api_key.get_secret_value():
        return GrokProvider(s)
    return None
