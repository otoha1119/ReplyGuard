"""analysis JSON から廃止された category キーを除去する.

Revision ID: 0009_drop_analysis_category
Revises: 0008_add_last_history_id
Create Date: 2026-06-14

AnalysisResult から category フィールドを削除し request_type に統合した
（extra="forbid" のため, 既存レコードに category が残っていると読み込みに失敗する）.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_drop_analysis_category"
down_revision = "0008_add_last_history_id"
branch_labels = None
depends_on = None

message_records = sa.table(
    "message_records",
    sa.column("message_id", sa.String),
    sa.column("analysis", sa.JSON),
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(message_records.c.message_id, message_records.c.analysis)
    ).fetchall()
    for message_id, analysis in rows:
        if isinstance(analysis, dict) and "category" in analysis:
            updated = {k: v for k, v in analysis.items() if k != "category"}
            bind.execute(
                sa.update(message_records)
                .where(message_records.c.message_id == message_id)
                .values(analysis=updated)
            )


def downgrade() -> None:
    # category の値は失われているため復元しない（不可逆）.
    pass
