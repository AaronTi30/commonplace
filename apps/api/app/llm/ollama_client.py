from __future__ import annotations

import httpx

from app.settings import settings


class OllamaClient:
    """Thin wrapper around Ollama's HTTP API (``/api/generate``)."""

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

    def generate(self, prompt: str) -> str:
        url = f"{self._base}/api/generate"
        payload = {"model": self._model, "prompt": prompt, "stream": False}
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return (data.get("response") or "").strip()


def get_ollama_client() -> OllamaClient:
    return OllamaClient()
