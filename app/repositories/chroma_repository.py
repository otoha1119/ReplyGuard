"""ChromaDB ベクトルストア実装.

フィードバックの埋め込みベクトルを永続化し, 類似検索を提供する.
コレクション名は "email_feedback_v1"（スキーマ変更時はインクリメントする）.
Chroma のメタデータは str/int/float/bool のみ許容されるため bool は int で保存する.
"""

import logging
from pathlib import Path

import chromadb

from app.ports.vector_store import FeedbackEntry

logger = logging.getLogger(__name__)

_COLLECTION = "email_feedback_v1"


class ChromaRepository:
    """VectorStore ポートの ChromaDB 実装."""

    def __init__(self, path: str) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(
            _COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB 初期化: path=%s collection=%s count=%d", path, _COLLECTION, self._col.count())

    def add_feedback(
        self,
        doc_id: str,
        embedding: list[float],
        text: str,
        importance: int,
        request_type: str,
        is_promotional: bool,
        is_security_notification: bool,
        reason: str,
    ) -> None:
        self._col.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "importance": importance,
                "request_type": request_type,
                "is_promotional": int(is_promotional),
                "is_security_notification": int(is_security_notification),
                "reason": reason[:300],
            }],
        )
        logger.info("フィードバック保存: doc_id=%s importance=%d request_type=%s", doc_id, importance, request_type)

    def query_similar(self, embedding: list[float], top_k: int = 3) -> list[FeedbackEntry]:
        count = self._col.count()
        if count == 0:
            return []
        n = min(top_k, count)
        results = self._col.query(query_embeddings=[embedding], n_results=n)
        entries = []
        for i, meta in enumerate(results["metadatas"][0]):
            entries.append(FeedbackEntry(
                text=(results["documents"][0][i] or "")[:200],
                importance=int(meta["importance"]),
                request_type=str(meta["request_type"]),
                is_promotional=bool(meta["is_promotional"]),
                is_security_notification=bool(meta["is_security_notification"]),
                reason=str(meta.get("reason", "")),
                distance=float(results["distances"][0][i]),
            ))
        return entries
