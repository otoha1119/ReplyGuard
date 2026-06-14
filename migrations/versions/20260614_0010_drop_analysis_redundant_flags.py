"""analysis JSON から廃止された needs_reply/has_deadline/is_direct キーを除去する.

Revision ID: 0010_drop_analysis_redundant_flags
Revises: 0009_drop_analysis_category
Create Date: 2026-06-14

AnalysisResult から needs_reply/has_deadline/is_direct を削除した
（request_type / deadline と重複するため. extra="forbid" のため,
既存レコードにこれらのキーが残っていると読み込みに失敗する）.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_drop_analysis_redundant_flags"
down_revision = "0009_drop_analysis_category"
branch_labels = None
depends_on = None

_REMOVED_KEYS = ("needs_reply", "has_deadline", "is_direct")

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
        if isinstance(analysis, dict) and any(k in analysis for k in _REMOVED_KEYS):
            updated = {k: v for k, v in analysis.items() if k not in _REMOVED_KEYS}
            bind.execute(
                sa.update(message_records)
                .where(message_records.c.message_id == message_id)
                .values(analysis=updated)
            )


def downgrade() -> None:
    # 値は失われているため復元しない（不可逆）.
    pass
