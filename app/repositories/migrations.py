"""起動時の自動マイグレーション.

create_all は新規テーブルの作成のみで既存テーブルへの列追加は行わない.
そのため, migrations 追加前に create_all で作られた DB（列が不足した
旧スキーマ）でも, 起動時に alembic head まで自動追従させる（冪等）.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.repositories import db

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def run_migrations(database_url: str) -> None:
    """DB を alembic head まで追従させる."""
    cfg = _alembic_config(database_url)
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if "alembic_version" in tables:
        command.upgrade(cfg, "head")
        return

    if "message_records" not in tables:
        # 真の新規 DB. migrations が一から作成する.
        command.upgrade(cfg, "head")
        return

    columns = {c["name"] for c in inspector.get_columns("message_records")}
    if "account_address" in columns:
        # create_all が最新スキーマで作成済み. 適用済みとして記録するだけ.
        command.stamp(cfg, "head")
        return

    # migrations 追加前の create_all で作られた旧スキーマ. 0001 相当として
    # 記録した上で残りの差分（列追加）を適用する.
    command.stamp(cfg, "0001_initial")
    command.upgrade(cfg, "head")
