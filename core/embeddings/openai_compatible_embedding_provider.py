import json
import urllib.error
import urllib.request
from typing import Any

from configs import get_settings
from core.optimization import embedding_cache


class OpenAICompatibleEmbeddingProvider:
    """Minimal OpenAI-compatible embeddings client using stdlib HTTP."""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.embedding_api_key
        self.api_base = (api_base or settings.embedding_api_base).rstrip("/")
        self.model = model or settings.embedding_model

    def embed_text(self, text: str) -> list[float]:
        cache_key = {
            "provider": self.api_base,
            "model": self.model,
            "text": text.strip(),
        }
        cached = embedding_cache.get(cache_key)
        if cached is not None:
            return cached
        if not self.api_key or "your-embedding-key" in self.api_key or self.api_key.endswith("-here"):
            raise RuntimeError(
                "EMBEDDING_API_KEY must be set. Use 'ollama' for local Ollama embeddings, "
                "or a real provider API key for hosted embedding endpoints."
            )

        payload = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Embedding API request failed with HTTP {exc.code}. "
                "Check EMBEDDING_API_KEY, EMBEDDING_API_BASE, and EMBEDDING_MODEL. "
                f"Response: {error_body}"
            ) from exc

        embedding = [float(value) for value in body["data"][0]["embedding"]]
        embedding_cache.set(cache_key, embedding)
        return embedding
