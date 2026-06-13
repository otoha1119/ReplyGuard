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

    get_msg = {
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

    # INBOX のみ 1 件, SPAM は空にして重複を防ぐ.
    def list_side_effect(*, userId, maxResults, labelIds):
        messages = [{"id": "msg1"}] if labelIds == ["INBOX"] else []
        result = MagicMock()
        result.execute.return_value = {"messages": messages}
        return result

    mock_service.users.return_value.messages.return_value.list.side_effect = list_side_effect
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = get_msg

    with patch.object(src, "_build_service", return_value=mock_service):
        emails = src.list_recent(limit=1)

    assert len(emails) == 1
    assert emails[0].subject == "テスト件名"
    assert emails[0].is_unread is True
    assert emails[0].provider == "gmail"
    assert emails[0].sender == "sender@example.com"
    assert emails[0].is_spam is False


def test_list_recent_spam_messages_marked_is_spam() -> None:
    """SPAM ラベルで取得したメールは is_spam=True になる."""
    src, _ = _make_source()
    mock_service = MagicMock()

    spam_msg = {
        "id": "spam1",
        "snippet": "迷惑スニペット",
        "labelIds": ["SPAM"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "迷惑件名"},
                {"name": "From", "value": "spam@evil.example"},
                {"name": "To", "value": "me@gmail.com"},
                {"name": "Date", "value": "Fri, 13 Jun 2026 12:00:00 +0000"},
            ],
            "body": {"data": "c3BhbQ=="},  # "spam" の base64
        },
    }

    def list_side_effect(*, userId, maxResults, labelIds):
        messages = [{"id": "spam1"}] if labelIds == ["SPAM"] else []
        result = MagicMock()
        result.execute.return_value = {"messages": messages}
        return result

    mock_service.users.return_value.messages.return_value.list.side_effect = list_side_effect
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = spam_msg

    with patch.object(src, "_build_service", return_value=mock_service):
        emails = src.list_recent(limit=1)

    assert len(emails) == 1
    assert emails[0].is_spam is True
    assert emails[0].subject == "迷惑件名"


def test_list_recent_total_capped_at_limit() -> None:
    """INBOX + SPAM の合計が limit を超える場合, limit 件に絞る."""
    src, _ = _make_source()
    mock_service = MagicMock()

    def list_side_effect(*, userId, maxResults, labelIds):
        messages = [{"id": f"{labelIds[0]}-{i}"} for i in range(3)]
        r = MagicMock()
        r.execute.return_value = {"messages": messages}
        return r

    def get_side_effect(*, userId, id, format):
        r = MagicMock()
        r.execute.return_value = {
            "id": id,
            "snippet": "",
            "labelIds": [],
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": id},
                    {"name": "From", "value": "x@example.com"},
                    {"name": "To", "value": "me@gmail.com"},
                    {"name": "Date", "value": "Fri, 13 Jun 2026 12:00:00 +0000"},
                ],
                "body": {"data": ""},
            },
        }
        return r

    mock_service.users.return_value.messages.return_value.list.side_effect = list_side_effect
    mock_service.users.return_value.messages.return_value.get.side_effect = get_side_effect

    with patch.object(src, "_build_service", return_value=mock_service):
        emails = src.list_recent(limit=4)

    assert len(emails) == 4


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
