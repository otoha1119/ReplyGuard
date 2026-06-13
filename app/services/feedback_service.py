"""フィードバックサービス.

ユーザーの修正内容をテキスト埋め込みに変換してベクトル DB に保存する.
埋め込みテキストは「件名＋差出人＋スニペット」のみ（本文は送らない）.
Ollama またはベクトル DB が使えない場合は警告ログのみで続行する.
"""

import logging
from datetime import datetime, timezone

from app.adapters.embedding.ollama_embed import OllamaEmbedding
from app.models import FeedbackCorrection
from app.ports.errors import NotFoundError
from app.ports.repository import Repository
from app.ports.vector_store import VectorStore

logger = logging.getLogger(__name__)


class FeedbackService:
    """フィードバックを埋め込みベクトルに変換して VectorStore に保存する."""

    def __init__(
        self,
        repo: Repository,
        embedding: OllamaEmbedding,
        vector_store: VectorStore,
    ) -> None:
        self._repo = repo
        self._embedding = embedding
        self._vector_store = vector_store

    def submit(self, message_id: str, correction: FeedbackCorrection) -> None:
        """フィードバックを保存する. メッセージが存在しない場合は NotFoundError."""
        record = self._repo.get(message_id)
        if record is None:
            raise NotFoundError(f"message_id={message_id} は存在しません")

        email = record.email
        embed_text = f"{email.subject}\n{email.sender}\n{email.snippet}"

        try:
            vector = self._embedding.embed(embed_text)
        except Exception as exc:
            logger.warning("embedding 失敗（フィードバックはスキップ）: %s", type(exc).__name__)
            return

        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        doc_id = f"{message_id}__{ts}"

        try:
            self._vector_store.add_feedback(
                doc_id=doc_id,
                embedding=vector,
                text=embed_text,
                importance=correction.importance,
                request_type=correction.request_type,
                is_promotional=correction.is_promotional,
                is_security_notification=correction.is_security_notification,
                reason=correction.reason,
            )
        except Exception as exc:
            logger.warning("ベクトル DB 書き込み失敗: %s", type(exc).__name__)
