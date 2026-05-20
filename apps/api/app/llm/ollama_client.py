from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from app.settings import settings


class OllamaClient:
    """Thin wrapper around Ollama's /api/chat endpoint.

    Uses the chat endpoint (not /api/generate) so that instruction-tuned models
    (llama3.1, phi3, gemma2, mistral-nemo, etc.) apply their chat templates and
    actually follow the prompt instructions rather than treating them as text to
    complete.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._base = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._timeout = timeout_seconds if timeout_seconds is not None else settings.ollama_timeout_seconds

    def _messages(self, prompt: str) -> list[dict[str, str]]:
        return [{"role": "user", "content": prompt}]

    def generate(self, prompt: str) -> str:
        url = f"{self._base}/api/chat"
        payload = {"model": self._model, "messages": self._messages(prompt), "stream": False}
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return (data.get("message", {}).get("content") or "").strip()

    async def stream_generate(self, prompt: str) -> AsyncGenerator[str, None]:
        """Yield response tokens one at a time from Ollama's streaming chat API."""
        url = f"{self._base}/api/chat"
        payload = {"model": self._model, "messages": self._messages(prompt), "stream": True}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break


def get_ollama_client() -> OllamaClient:
    return OllamaClient()
