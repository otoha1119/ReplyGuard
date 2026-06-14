"""Ollama embedding アダプタ.

Ollama の /api/embed エンドポイントを叩いてテキストを埋め込みベクトルへ変換する.
LLM と同一サーバ上の embedding モデル（例: multilingual-e5-small）を使う.

セキュリティ:
- 送信するのは件名・差出人・スニペットのみ（本文全文は送らない）.
- API キー不要（Ollama はローカル/LAN 内サーバ）.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


class OllamaEmbedding:
    """Ollama /api/embed を使った同期 embedding アダプタ."""

    def __init__(self, base_url: str, model: str, timeout: int = 30) -> None:
        self._url = base_url.rstrip("/") + "/api/embed"
        self._model = model
        self._timeout = timeout

    def embed(self, text: str) -> list[float]:
        """テキストを埋め込みベクトルへ変換する.

        Ollama /api/embed レスポンス: {"embeddings": [[...float...]]}
        """
        resp = httpx.post(
            self._url,
            json={"model": self._model, "input": text},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if not embeddings:
            raise ValueError(f"Ollama embedding レスポンスに embeddings がありません: {list(data.keys())}")
        first = embeddings[0]
        return first if isinstance(first, list) else embeddings
