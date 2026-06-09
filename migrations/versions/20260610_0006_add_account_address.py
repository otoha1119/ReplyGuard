"""account_address カラムを message_records に追加.

Revision ID: 0006_add_account_address
Revises: 0005_add_account_configs
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_account_address"
down_revision = "0005_add_account_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "message_records",
        sa.Column("account_address", sa.String(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_message_records_account_address",
        "message_records",
        ["account_address"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_records_account_address", table_name="message_records")
    op.drop_column("message_records", "account_address")
