"""GmailApiSource の単体テスト."""
from unittest.mock import MagicMock, patch

import google.auth.exceptions

from app.adapters.sources.gmail_api import GmailApiSource


def _make_source(account_id: str = "acc1") -> tuple[GmailApiSource, MagicMock]:
    mock_repo = MagicMock()
    src = GmailApiSource(
        refresh_token="rt",
        client_id="cid",
        client_secret="cs",
        account_id=account_id,
        account_repo=mock_repo,
    )
    return src, mock_repo


def test_close_is_noop() -> None:
    src, _ = _make_source()
    src.close()  # 例外なし


def test_list_recent_maps_to_email_messages() -> None:
    src, _ = _make_source()
    mock_service = MagicMock()

    # messages.list
    mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "msg1"}]
    }
    # messages.get
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "msg1",
        "snippet": "テストスニペット",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "テスト件名"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "me@gmail.com"},
                {"name": "Date", "value": "Fri, 13 Jun 2026 12:00:00 +0000"},
            ],
            "body": {"data": "dGVzdA=="},  # "test" の base64
        },
    }

    with patch.object(src, "_build_service", return_value=mock_service):
        emails = src.list_recent(limit=1)

    assert len(emails) == 1
    assert emails[0].subject == "テスト件名"
    assert emails[0].is_unread is True
    assert emails[0].provider == "gmail"
    assert emails[0].sender == "sender@example.com"


def test_list_recent_refresh_error_sets_reauth_required() -> None:
    src, mock_repo = _make_source()
    with patch.object(
        src,
        "_build_service",
        side_effect=google.auth.exceptions.RefreshError("expired"),
    ):
        try:
            src.list_recent()
        except google.auth.exceptions.RefreshError:
            pass

    mock_repo.set_auth_status.assert_called_once_with("acc1", "reauth_required")


# --- detect_changes -------------------------------------------------------

def test_detect_changes_initial_returns_empty_and_cursor() -> None:
    """初回（start_cursor=None）は差分なし・現在 historyId を返す."""
    src, _ = _make_source()
    mock_service = MagicMock()
    mock_service.users.return_value.getProfile.return_value.execute.return_value = {
        "historyId": "100"
    }
    with patch.object(src, "_build_service", return_value=mock_service):
        removed, cursor = src.detect_changes(None)
    assert removed == []
    assert cursor == "100"


def test_detect_changes_returns_archived_and_deleted() -> None:
    """labelsRemoved INBOX → archived, labelsAdded TRASH → deleted."""
    src, _ = _make_source()
    mock_service = MagicMock()
    mock_service.users.return_value.history.return_value.list.return_value.execute.return_value = {
        "historyId": "200",
        "history": [
            {
                "labelsRemoved": [
                    {"message": {"id": "arch1"}, "labelIds": ["INBOX"]}
                ],
                "labelsAdded": [
                    {"message": {"id": "del1"}, "labelIds": ["TRASH"]}
                ],
                "messagesDeleted": [],
            }
        ],
    }
    with patch.object(src, "_build_service", return_value=mock_service):
        removed, cursor = src.detect_changes("100")

    kinds = {r.raw_id: r.kind for r in removed}
    assert kinds["arch1"] == "archived"
    assert kinds["del1"] == "deleted"
    assert cursor == "200"


def test_detect_changes_deleted_takes_priority_over_archived() -> None:
    """同一メッセージが labelsRemoved INBOX かつ labelsAdded TRASH → deleted 優先."""
    src, _ = _make_source()
    mock_service = MagicMock()
    mock_service.users.return_value.history.return_value.list.return_value.execute.return_value = {
        "historyId": "300",
        "history": [
            {
                "labelsRemoved": [
                    {"message": {"id": "both1"}, "labelIds": ["INBOX"]}
                ],
                "labelsAdded": [
                    {"message": {"id": "both1"}, "labelIds": ["TRASH"]}
                ],
                "messagesDeleted": [],
            }
        ],
    }
    with patch.object(src, "_build_service", return_value=mock_service):
        removed, _ = src.detect_changes("200")

    assert len(removed) == 1
    assert removed[0].raw_id == "both1"
    assert removed[0].kind == "deleted"


def test_detect_changes_404_resets_cursor() -> None:
    """startHistoryId 失効（404）→ 差分なし・現在カーソルへリセット."""
    from googleapiclient.errors import HttpError
    src, _ = _make_source()
    mock_service = MagicMock()

    resp_mock = MagicMock()
    resp_mock.status = 404
    http_err = HttpError(resp=resp_mock, content=b"Not Found")
    mock_service.users.return_value.history.return_value.list.return_value.execute.side_effect = http_err
    mock_service.users.return_value.getProfile.return_value.execute.return_value = {
        "historyId": "999"
    }
    with patch.object(src, "_build_service", return_value=mock_service):
        removed, cursor = src.detect_changes("old_cursor")

    assert removed == []
    assert cursor == "999"
