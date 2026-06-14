"""受信・正規化層のポート.

取得元（Gmail IMAP / 将来 Outlook 等）の差を吸収し, 共通スキーマ
EmailMessage の列を返す契約. adapter（app/adapters/sources/*）が実装する.

baseline は list_recent(limit) のみで動く（最新 N 件を再取得し,
Repository.upsert で message_id 冪等にして重複を防ぐ）. 増分同期は
将来 fetch_since で足せる（今は必須にしない）.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.models import EmailMessage


@runtime_checkable
class MessageSource(Protocol):
    """プロバイダ非依存のメール取得口."""

    def list_recent(self, limit: int = 10) -> list[EmailMessage]:
        """受信トレイの最新メールを新しい順で返す（読み取り専用）."""
        ...

    def close(self) -> None:
        """接続を閉じる（接続を持たない実装では no-op で良い）."""
        ...


@dataclass(frozen=True)
class RemovedMessage:
    """受信トレイから消えたメッセージ1件と，その種別."""

    raw_id: str                           # 取得元の生 ID（make_id 前．Gmail はメッセージ ID）
    kind: Literal["archived", "deleted"]  # archived=INBOX から外れた / deleted=削除


@runtime_checkable
class RemovalDetectingSource(Protocol):
    """受信トレイからの削除/アーカイブ差分を検知できる source（optional 拡張）."""

    def detect_changes(
        self, start_cursor: str | None
    ) -> tuple[list[RemovedMessage], str | None]:
        """前回カーソル以降に INBOX から消えたメッセージと，新しいカーソルを返す.

        - start_cursor=None は初回. 差分は空 list で返し, 現在カーソルだけ確立する.
        - 戻りカーソルが None の場合, 呼び出し側は保存をスキップする.
        - 読み取り専用（書き込みは行わない）.
        """
        ...
