"""ベクトルストアのポート."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FeedbackEntry:
    """ベクトルストアから取得した類似フィードバック 1 件."""

    text: str           # 埋め込みに使ったテキスト（件名+差出人+スニペット）
    importance: int
    request_type: str
    is_promotional: bool
    is_security_notification: bool
    reason: str
    distance: float     # コサイン距離（小さいほど近い）


@runtime_checkable
class VectorStore(Protocol):
    """フィードバックの埋め込み保存・類似検索の契約."""

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
    ) -> None: ...

    def query_similar(
        self, embedding: list[float], top_k: int = 3
    ) -> list[FeedbackEntry]: ...
