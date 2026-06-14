"""provider 列を message_records に追加

Revision ID: 0003_add_provider
Revises: 0002_add_is_archived
Create Date: 2026-06-09

プロバイダ別フィルタを SQL レベルで高速化するため非正規化列を追加する.
既存レコードは email JSON 内の $.provider をバックフィルする.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_provider"
down_revision: Union[str, None] = "0002_add_is_archived"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "message_records",
        sa.Column(
            "provider",
            sa.String(),
            nullable=False,
            server_default=sa.text("'gmail'"),
        ),
    )
    op.create_index(
        "ix_message_records_provider", "message_records", ["provider"]
    )
    # 既存レコードを email JSON から backfill する（SQLite の json_extract を使用）.
    op.execute(
        "UPDATE message_records "
        "SET provider = json_extract(email, '$.provider') "
        "WHERE provider IS NULL OR provider = ''"
    )


def downgrade() -> None:
    op.drop_index("ix_message_records_provider", table_name="message_records")
    op.drop_column("message_records", "provider")
