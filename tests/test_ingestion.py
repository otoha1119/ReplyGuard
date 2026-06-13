"""IngestionService のコスト対策（analyze-once）を検証する.

分析（LLM）は 1 メールにつき生涯 1 回だけ呼ぶ. 同じメールを再取得しても
2 度目以降は保存済みの analysis を再利用し, analyzer を呼び直さない
（従量課金の抑制）. 期限依存の triage/urgency スコアは毎サイクル再計算される.
"""

from types import SimpleNamespace

import pytest

from app.models import AnalysisResult, EmailMessage
from app.repositories import db
from app.repositories.sql_repository import SqlRepository
from app.services.ingestion import IngestionService

from tests.conftest import make_email


class CountingAnalyzer:
    """analyze 呼び出し回数を数えるフェイク analyzer."""

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, email: EmailMessage) -> AnalysisResult:
        self.calls += 1
        return AnalysisResult(
            importance=4,
            needs_reply=True,
            task_weight="medium",
            category="action_required",
            summary="要約",
            reason="テスト",
            analyzer="fake",
        )


class FakeSource:
    """固定のメール群を返す読み取り専用フェイクソース."""

    def __init__(self, emails: list[EmailMessage], address: str = "me@example.com"):
        self._emails = emails
        self.address = address

    def list_recent(self, limit: int = 10) -> list[EmailMessage]:
        return self._emails[:limit]

    def close(self) -> None:
        return None


class NullNotifier:
    def notify(self, record, dedupe_key: str) -> bool:
        return False


def _make_service(source: FakeSource, analyzer: CountingAnalyzer) -> IngestionService:
    settings = SimpleNamespace(
        ingest_limit=10,
        notify_importance_threshold=4,
        llm_max_body_chars=4000,
        gmail_address="",
        gmail_app_password="",
    )
    service = IngestionService(
        account_repo=None,
        analyzer=analyzer,
        repo=SqlRepository(),
        notifier=NullNotifier(),
        settings=settings,
    )
    # 実ソース構築（IMAP 接続）を避け, フェイクソースに差し替える.
    service._build_sources = lambda: [source]
    return service


@pytest.fixture(autouse=True)
def _inmemory_db():
    db.configure_engine("sqlite:///:memory:")
    db.init_db()


def test_analyze_is_called_once_across_reingest():
    emails = [make_email("1"), make_email("2")]
    analyzer = CountingAnalyzer()
    service = _make_service(FakeSource(emails), analyzer)

    first = service.run_once()
    assert first["fetched"] == 2
    assert first["inserted"] == 2
    assert analyzer.calls == 2  # 新着 2 件を分析

    # 同じメールを再取得しても analyze は呼ばれない（保存済み結果を再利用）.
    second = service.run_once()
    assert second["fetched"] == 2
    assert second["inserted"] == 0
    assert analyzer.calls == 2  # ★増えない


def test_new_email_in_second_cycle_is_analyzed_only_once():
    analyzer = CountingAnalyzer()
    source = FakeSource([make_email("1")])
    service = _make_service(source, analyzer)

    service.run_once()
    assert analyzer.calls == 1

    # 2 通目が増えたサイクル: 既存 1 は再利用, 新着 1 のみ分析.
    source._emails = [make_email("1"), make_email("2")]
    service.run_once()
    assert analyzer.calls == 2


def test_reused_analysis_is_persisted():
    analyzer = CountingAnalyzer()
    service = _make_service(FakeSource([make_email("1")]), analyzer)
    service.run_once()
    service.run_once()

    record = service._repo.get("gmail:1")
    assert record is not None
    assert record.analysis is not None
    assert record.analysis.importance == 4
