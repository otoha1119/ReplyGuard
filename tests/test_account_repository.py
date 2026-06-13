"""AccountRepository の単体テスト（SQLite in-memory）."""

import pytest

from app.repositories import db
from app.repositories.account_repository import AccountRepository


@pytest.fixture
def acc_repo():
    db.configure_engine("sqlite:///:memory:")
    db.init_db()
    return AccountRepository()


def _create_oauth_account(repo: AccountRepository) -> str:
    acc = repo.create_oauth(
        provider="gmail",
        label="test",
        address="test@example.com",
        refresh_token="rt",
    )
    return acc.id


# --- last_history_id カーソル read/write -----------------------------------

def test_get_history_id_returns_none_for_new_account(acc_repo):
    account_id = _create_oauth_account(acc_repo)
    assert acc_repo.get_history_id(account_id) is None


def test_set_and_get_history_id(acc_repo):
    account_id = _create_oauth_account(acc_repo)
    acc_repo.set_history_id(account_id, "12345")
    assert acc_repo.get_history_id(account_id) == "12345"


def test_set_history_id_overwrites(acc_repo):
    account_id = _create_oauth_account(acc_repo)
    acc_repo.set_history_id(account_id, "100")
    acc_repo.set_history_id(account_id, "200")
    assert acc_repo.get_history_id(account_id) == "200"


def test_get_history_id_missing_account_returns_none(acc_repo):
    assert acc_repo.get_history_id("nonexistent-id") is None


def test_set_history_id_missing_account_is_noop(acc_repo):
    # 存在しない ID への set は例外なし・何もしない.
    acc_repo.set_history_id("nonexistent-id", "999")
