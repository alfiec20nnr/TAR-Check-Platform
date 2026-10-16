"""Add searches.location (encrypted at rest) — an optional town/city/region
used to narrow web searches for people with common or famous names.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("searches", sa.Column("location", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("searches", "location")
