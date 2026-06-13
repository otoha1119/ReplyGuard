"""account_configs に Gmail History API カーソル列を追加.

Revision ID: 0008_add_last_history_id
Revises: 0007_add_oauth_columns
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_last_history_id"
down_revision = "0007_add_oauth_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("account_configs") as batch_op:
        batch_op.add_column(sa.Column("last_history_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("account_configs") as batch_op:
        batch_op.drop_column("last_history_id")
