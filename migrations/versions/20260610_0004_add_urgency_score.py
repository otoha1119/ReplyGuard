"""urgency_score 列を message_records に追加

Revision ID: 0004_add_urgency_score
Revises: 0003_add_provider
Create Date: 2026-06-10

期限（deadline）の近接度から算出した緊急度スコアを非正規化列として保存する.
既存レコードは analysis JSON 内の deadline をもとに再計算しないため 0.0 に初期化する.
次回の ingest 実行時に urgency_score が更新される.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_urgency_score"
down_revision: Union[str, None] = "0003_add_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "message_records",
        sa.Column(
            "urgency_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("message_records", "urgency_score")
