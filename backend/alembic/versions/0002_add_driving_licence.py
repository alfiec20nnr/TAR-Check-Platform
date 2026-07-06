"""Add searches.driving_licence_number (encrypted at rest) for the DVLA check.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "searches",
        sa.Column("driving_licence_number", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("searches", "driving_licence_number")
