"""IngestionService の追随同期ステップのテスト.

_sync_remote_changes の振る舞いを importance しきい値・source 種別・フラグで検証する.
実 Gmail / LLM は叩かない（fake source・fake repo・fake account_repo）.
"""

from unittest.mock import MagicMock, call

import pytest

from app.adapters.sources.gmail_api import GmailApiSource
from app.models import AnalysisResult, MessageRecord
from app.ports.source import RemovedMessage, RemovalDetectingSource
from app.services.ingestion import IngestionService
from tests.conftest import make_record


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

class FakeDetectingSource:
    """RemovalDetectingSource を満たす最小 fake."""

    def __init__(self, removed: list[RemovedMessage], new_cursor: str | None = "cur2"):
        self._removed = removed
        self._new_cursor = new_cursor

    def detect_changes(
        self, start_cursor: str | None
    ) -> tuple[list[RemovedMessage], str | None]:
        return self._removed, self._new_cursor

    # list_recent / close / address は _sync_remote_changes では不要
    # （run_once 全体を回す場合は追加が必要）


class FakeNonDetectingSource:
    """RemovalDetectingSource を持たない source（IMAP/Slack 相当）."""

    def list_recent(self, limit: int = 10):
        return []

    def close(self) -> None:
        pass

    @property
    def address(self) -> str:
        return "test@example.com"


def _make_service(
    *,
    sync: bool = True,
    threshold: int = 3,
    sources_with_accs: list | None = None,
) -> tuple[IngestionService, MagicMock, MagicMock]:
    """テスト用 IngestionService を生成. repo と account_repo の MagicMock を返す."""
    mock_repo = MagicMock()
    mock_account_repo = MagicMock()
    mock_analyzer = MagicMock()
    mock_notifier = MagicMock()
    mock_settings = MagicMock()
    mock_settings.sync_remote_changes = sync
    mock_settings.auto_archive_importance_threshold = threshold
    mock_settings.ingest_limit = 10
    mock_settings.notify_importance_threshold = 4

    svc = IngestionService(
        account_repo=mock_account_repo,
        analyzer=mock_analyzer,
        repo=mock_repo,
        notifier=mock_notifier,
        settings=mock_settings,
    )

    # _build_sources をモンキーパッチして sources_with_accs を返す
    if sources_with_accs is not None:
        svc._build_sources = lambda: sources_with_accs

    return svc, mock_repo, mock_account_repo


# ---------------------------------------------------------------------------
# _sync_remote_changes のテスト
# ---------------------------------------------------------------------------

def test_sync_deletes_low_importance_deleted_message() -> None:
    """importance=2 の deleted → repo.delete が呼ばれる."""
    removed = [RemovedMessage("msg1", "deleted")]
    src = FakeDetectingSource(removed, new_cursor="cur2")
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cur1"

    rec = make_record("msg1", analysis=AnalysisResult(importance=2))
    mock_repo.get.return_value = rec

    svc._sync_remote_changes([(src, acc)])

    mock_repo.delete.assert_called_once_with("gmail:msg1")
    mock_repo.set_archived.assert_not_called()
    mock_account_repo.set_history_id.assert_called_once_with("acc1", "cur2")


def test_sync_archives_low_importance_archived_message() -> None:
    """importance=2 の archived → repo.set_archived(id, True) が呼ばれる."""
    removed = [RemovedMessage("msg2", "archived")]
    src = FakeDetectingSource(removed, new_cursor="cur2")
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cur1"

    rec = make_record("msg2", analysis=AnalysisResult(importance=3))
    mock_repo.get.return_value = rec

    svc._sync_remote_changes([(src, acc)])

    mock_repo.set_archived.assert_called_once_with("gmail:msg2", True)
    mock_repo.delete.assert_not_called()


def test_sync_skips_high_importance_deleted() -> None:
    """importance=5 の deleted → 何もしない（残す）."""
    removed = [RemovedMessage("msg3", "deleted")]
    src = FakeDetectingSource(removed)
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cur1"

    rec = make_record("msg3", analysis=AnalysisResult(importance=5))
    mock_repo.get.return_value = rec

    svc._sync_remote_changes([(src, acc)])

    mock_repo.delete.assert_not_called()
    mock_repo.set_archived.assert_not_called()


def test_sync_skips_high_importance_archived() -> None:
    """importance=4 の archived → 何もしない."""
    removed = [RemovedMessage("msg4", "archived")]
    src = FakeDetectingSource(removed)
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cur1"

    rec = make_record("msg4", analysis=AnalysisResult(importance=4))
    mock_repo.get.return_value = rec

    svc._sync_remote_changes([(src, acc)])

    mock_repo.delete.assert_not_called()
    mock_repo.set_archived.assert_not_called()


def test_sync_skips_message_with_no_analysis() -> None:
    """analysis=None の場合 → 何もしない（安全側）."""
    removed = [RemovedMessage("msg5", "deleted")]
    src = FakeDetectingSource(removed)
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cur1"

    rec = make_record("msg5", analysis=None)
    mock_repo.get.return_value = rec

    svc._sync_remote_changes([(src, acc)])

    mock_repo.delete.assert_not_called()
    mock_repo.set_archived.assert_not_called()


def test_sync_skips_message_not_in_db() -> None:
    """DB にない message_id（get=None）は何もしない."""
    removed = [RemovedMessage("msg_gone", "deleted")]
    src = FakeDetectingSource(removed)
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cur1"
    mock_repo.get.return_value = None

    svc._sync_remote_changes([(src, acc)])

    mock_repo.delete.assert_not_called()
    mock_repo.set_archived.assert_not_called()


def test_sync_skips_non_detecting_source() -> None:
    """RemovalDetectingSource を持たない source（IMAP/Slack）はスキップ."""
    src = FakeNonDetectingSource()
    acc = {"id": "acc1", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()

    svc._sync_remote_changes([(src, acc)])

    mock_repo.delete.assert_not_called()
    mock_repo.set_archived.assert_not_called()
    mock_account_repo.get_history_id.assert_not_called()


def test_sync_skips_when_flag_disabled() -> None:
    """sync_remote_changes=False のとき _sync_remote_changes は呼ばれない（run_once 経由）."""
    removed = [RemovedMessage("msg_x", "deleted")]
    src = FakeDetectingSource(removed)
    acc = {"id": "acc1", "provider": "gmail", "address": "x@example.com",
           "credential": "", "auth_type": "oauth", "refresh_token": "rt",
           "auth_status": "ok"}

    svc, mock_repo, mock_account_repo = _make_service(sync=False, sources_with_accs=[(src, acc)])
    mock_account_repo.get_history_id.return_value = "cur1"
    mock_repo.get.return_value = None

    # _sync_remote_changes をモニター
    call_count = []
    original = svc._sync_remote_changes
    def counting_sync(pairs):
        call_count.append(1)
        return original(pairs)
    svc._sync_remote_changes = counting_sync

    svc.run_once()

    assert len(call_count) == 0, "_sync_remote_changes should not be called when flag is off"


def test_sync_saves_new_cursor() -> None:
    """detect_changes が返した new_cursor が set_history_id に渡される."""
    removed = []
    src = FakeDetectingSource(removed, new_cursor="cursor_new")
    acc = {"id": "acc2", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = "cursor_old"

    svc._sync_remote_changes([(src, acc)])

    mock_account_repo.set_history_id.assert_called_once_with("acc2", "cursor_new")


def test_sync_does_not_save_none_cursor() -> None:
    """detect_changes が None カーソルを返したら set_history_id は呼ばれない."""
    removed = []
    src = FakeDetectingSource(removed, new_cursor=None)
    acc = {"id": "acc2", "provider": "gmail"}

    svc, mock_repo, mock_account_repo = _make_service()
    mock_account_repo.get_history_id.return_value = None

    svc._sync_remote_changes([(src, acc)])

    mock_account_repo.set_history_id.assert_not_called()
