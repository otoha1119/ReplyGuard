"""GmailImapSource の正規化テスト.

実 IMAP は叩かない. imaplib.IMAP4_SSL をモックし, FETCH 応答（descriptor + raw bytes）
を GmailImapSource.list_recent が EmailMessage 列へ正規化することを検証する.
"""

from email.message import EmailMessage as MimeEmailMessage
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.sources import build_source
from app.adapters.sources.gmail_imap import GmailImapSource
from app.config import Settings
from app.models import EmailMessage
from app.ports.source import MessageSource


def _mime(
    *,
    subject: str = "件名",
    sender: str = "Alice <alice@example.com>",
    to: str = "me@example.com",
    date: str = "Mon, 09 Jun 2026 12:00:00 +0000",
    plain: str | None = "プレーン本文です。",
    html: str | None = None,
) -> bytes:
    """テスト用の MIME メールを生成して bytes 化する."""
    msg = MimeEmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = date
    if plain is not None and html is not None:
        msg.set_content(plain)
        msg.add_alternative(html, subtype="html")
    elif html is not None:
        msg.set_content(html, subtype="html")
    else:
        msg.set_content(plain or "")
    return msg.as_bytes()


def _fetch_item(uid: int, raw: bytes, *, seen: bool) -> tuple:
    """imap.fetch が返す 1 メッセージ分のタプル（descriptor, raw）を組む."""
    flags = "\\Seen" if seen else ""
    descriptor = f"{uid} (UID {uid} FLAGS ({flags}) BODY[]<0> {{{len(raw)}}}".encode()
    return (descriptor, raw)


def _make_imap_mock(
    items: list[tuple],
    total: int | None = None,
    *,
    spam_items: list[tuple] | None = None,
    spam_total: int | None = None,
    list_response: tuple | None = None,
) -> MagicMock:
    """IMAP4_SSL インスタンスのモックを組む. select/fetch/list/logout を擬装する.

    INBOX 以外への select は迷惑メールフォルダ扱いとし, spam_items/spam_total
    （既定は空）を返す. list_response は LIST 応答（\\Junk 検出用. 既定は空で
    見つからない＝既定名 [Gmail]/Spam にフォールバックする）.
    """
    imap = MagicMock()
    imap.login.return_value = ("OK", [b"ok"])
    n = total if total is not None else len(items)
    spam_items = spam_items or []
    spam_n = spam_total if spam_total is not None else len(spam_items)

    state = {"mailbox": "INBOX"}

    def select_side_effect(mailbox, readonly=True):
        state["mailbox"] = mailbox
        if mailbox == "INBOX":
            return ("OK", [str(n).encode()])
        return ("OK", [str(spam_n).encode()])

    def fetch_side_effect(seq_set, query):
        if state["mailbox"] == "INBOX":
            return ("OK", list(items))
        return ("OK", list(spam_items))

    imap.select.side_effect = select_side_effect
    imap.fetch.side_effect = fetch_side_effect
    imap.list.return_value = list_response if list_response is not None else ("OK", [])
    imap.logout.return_value = ("BYE", [b"bye"])
    return imap


# === Protocol 適合 ===

def test_satisfies_message_source_protocol() -> None:
    src = GmailImapSource("user@gmail.com", "pw")
    assert isinstance(src, MessageSource)


# === 正規化（plain 本文）===

def test_list_recent_normalizes_plain() -> None:
    raw = _mime(subject="こんにちは", plain="本文の中身\nもう一行")
    imap = _make_imap_mock([_fetch_item(42, raw, seen=False)])

    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        src = GmailImapSource("user@gmail.com", "pw")
        result = src.list_recent(limit=5)

    assert len(result) == 1
    m = result[0]
    assert isinstance(m, EmailMessage)
    assert m.id == "42"  # UID が安定 id
    assert m.provider == "gmail"
    assert m.subject == "こんにちは"
    assert m.sender == "Alice <alice@example.com>"
    assert m.to == ["me@example.com"]
    assert m.is_unread is True  # \Seen 無し → 未読
    assert m.received_at is not None
    assert "本文の中身" in (m.body_text or "")
    # snippet は空白を畳む（改行が空白に）
    assert m.snippet == "本文の中身 もう一行"
    assert m.is_spam is False
    # 読み取り専用: PEEK で fetch, readonly select（INBOX → 迷惑メールフォルダの順）
    first_call = imap.select.call_args_list[0]
    assert first_call.args[0] == "INBOX"
    assert first_call.kwargs.get("readonly") is True
    fetch_arg = imap.fetch.call_args.args[1]
    assert "BODY.PEEK[]" in fetch_arg


# === 既読判定 ===

def test_seen_flag_marks_read() -> None:
    raw = _mime()
    imap = _make_imap_mock([_fetch_item(7, raw, seen=True)])
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()
    assert result[0].is_unread is False


# === HTML 本文の素テキスト化 ===

def test_html_only_is_textified() -> None:
    html = "<html><body><h1>見出し</h1><p>段落の本文</p>"
    html += "<script>alert('x')</script></body></html>"
    raw = _mime(plain=None, html=html)
    imap = _make_imap_mock([_fetch_item(1, raw, seen=False)])
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()
    body = result[0].body_text or ""
    assert "見出し" in body
    assert "段落の本文" in body
    assert "<h1>" not in body  # タグは除去
    assert "alert" not in body  # script は除去


# === plain と html 両方 → plain 優先 ===

def test_plain_preferred_over_html() -> None:
    raw = _mime(plain="プレーン優先", html="<p>HTML側</p>")
    imap = _make_imap_mock([_fetch_item(1, raw, seen=False)])
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()
    body = result[0].body_text or ""
    assert "プレーン優先" in body
    assert "HTML側" not in body


# === 新しい順に並ぶ ===

def test_results_reversed_newest_first() -> None:
    items = [
        _fetch_item(10, _mime(subject="古い"), seen=False),
        _fetch_item(11, _mime(subject="新しい"), seen=False),
    ]
    imap = _make_imap_mock(items)
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()
    # fetch はシーケンス昇順で返る（10,11）→ 出力は新しい順（11,10）
    assert [m.id for m in result] == ["11", "10"]


# === snippet 長さ上限 ===

def test_snippet_truncated_to_limit() -> None:
    long_body = "あ" * 500
    raw = _mime(plain=long_body)
    imap = _make_imap_mock([_fetch_item(1, raw, seen=False)])
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()
    assert len(result[0].snippet) == 120


# === body_text の文字数上限 ===

def test_body_text_truncated_to_max_chars() -> None:
    long_body = "x" * 9000
    raw = _mime(plain=long_body)
    imap = _make_imap_mock([_fetch_item(1, raw, seen=False)])
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        src = GmailImapSource("user@gmail.com", "pw", max_body_chars=100)
        result = src.list_recent()
    assert len(result[0].body_text or "") == 100


# === 空の受信トレイ ===

def test_empty_inbox_returns_empty() -> None:
    imap = _make_imap_mock([], total=0)
    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()
    assert result == []
    imap.fetch.assert_not_called()  # 0 件なら fetch しない


# === 認証情報未設定 → RuntimeError ===

def test_missing_credentials_raises() -> None:
    src = GmailImapSource("", "")
    with pytest.raises(RuntimeError):
        src.list_recent()


# === build_source: settings から生成 ===

def test_build_source_uses_settings() -> None:
    settings = Settings(
        gmail_address="a@gmail.com",
        gmail_app_password="pw",
        llm_max_body_chars=1234,
    )
    src = build_source(settings)
    assert isinstance(src, GmailImapSource)
    assert isinstance(src, MessageSource)
    assert src._max_body_chars == 1234


# === close は no-op（例外を出さない）===

def test_close_is_noop() -> None:
    src = GmailImapSource("user@gmail.com", "pw")
    assert src.close() is None


# ===========================================================================
# 迷惑メール取得
# ===========================================================================

def test_spam_folder_discovered_via_junk_attribute_and_marked_is_spam() -> None:
    """\\Junk 属性で迷惑メールフォルダを検出し, is_spam=True で返す."""
    inbox_raw = _mime(subject="受信")
    spam_raw = _mime(subject="迷惑")
    list_resp = ("OK", [b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"'])
    imap = _make_imap_mock(
        [_fetch_item(1, inbox_raw, seen=False)],
        spam_items=[_fetch_item(2, spam_raw, seen=False)],
        list_response=list_resp,
    )

    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()

    assert len(result) == 2
    inbox_msg = next(m for m in result if m.subject == "受信")
    spam_msg = next(m for m in result if m.subject == "迷惑")
    assert inbox_msg.is_spam is False
    assert spam_msg.is_spam is True
    # 迷惑メールフォルダへの select も readonly=True
    second_call = imap.select.call_args_list[1]
    assert second_call.args[0] == "[Gmail]/Spam"
    assert second_call.kwargs.get("readonly") is True


def test_spam_folder_falls_back_to_default_name_when_list_fails() -> None:
    """LIST 失敗時は既定名 [Gmail]/Spam にフォールバックして取得を続ける."""
    spam_raw = _mime(subject="迷惑")
    imap = _make_imap_mock(
        [],
        total=0,
        spam_items=[_fetch_item(5, spam_raw, seen=False)],
    )
    imap.list.side_effect = Exception("LIST not supported")

    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()

    assert len(result) == 1
    assert result[0].is_spam is True
    second_call = imap.select.call_args_list[1]
    assert second_call.args[0] == "[Gmail]/Spam"


def test_spam_folder_failure_does_not_break_inbox() -> None:
    """迷惑メールフォルダの SELECT が失敗しても INBOX の結果は返す."""
    inbox_raw = _mime(subject="受信")
    imap = _make_imap_mock([_fetch_item(1, inbox_raw, seen=False)])

    original_side_effect = imap.select.side_effect

    def select_fail_spam(mailbox, readonly=True):
        if mailbox != "INBOX":
            return ("NO", [b"folder not found"])
        return original_side_effect(mailbox, readonly=readonly)

    imap.select.side_effect = select_fail_spam

    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()

    assert len(result) == 1
    assert result[0].subject == "受信"
    assert result[0].is_spam is False


def test_empty_spam_folder_returns_only_inbox() -> None:
    """迷惑メールフォルダが空のとき INBOX のみを返す."""
    raw = _mime(subject="INBOX の 1 件")
    imap = _make_imap_mock([_fetch_item(10, raw, seen=False)])

    with patch("app.adapters.sources.gmail_imap.imaplib.IMAP4_SSL", return_value=imap):
        result = GmailImapSource("user@gmail.com", "pw").list_recent()

    assert len(result) == 1
    assert result[0].is_spam is False
