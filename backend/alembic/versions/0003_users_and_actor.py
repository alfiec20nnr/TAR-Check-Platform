"""Multi-user accounts: users table, audit actor, search created_by.

Additive only, so existing local SQLite installs upgrade in place at boot.
The first user row is seeded from the legacy .env credentials by
app.seed.seed_default_user, not here (settings are not reliably available
inside alembic).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.add_column("audit_logs", sa.Column("actor", sa.String(100), nullable=True))
    op.add_column("searches", sa.Column("created_by", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("searches", "created_by")
    op.drop_column("audit_logs", "actor")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
