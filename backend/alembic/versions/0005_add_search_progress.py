"""Add searches.progress / progress_stage so the UI can show a real
progress bar while the search pipeline runs.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "searches",
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("searches", sa.Column("progress_stage", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("searches", "progress_stage")
    op.drop_column("searches", "progress")
