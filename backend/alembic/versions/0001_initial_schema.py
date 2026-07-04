"""Initial schema: searches, search_results, sources, reports, ai_summaries,
risk_scores, audit_logs.

Revision ID: 0001
Revises:
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("date_of_birth", sa.Text(), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_score_value", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=True),
        sa.Column("sources_searched", sa.JSON(), nullable=True),
    )
    op.create_index("ix_searches_status", "searches", ["status"])
    op.create_index("ix_searches_created_at", "searches", ["created_at"])
    op.create_index("ix_searches_risk_level", "searches", ["risk_level"])

    op.create_table(
        "search_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "search_id",
            sa.String(36),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("event_date", sa.String(32), nullable=True),
        sa.Column("subject_name", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_contribution", sa.Float(), nullable=False, server_default="0"),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_results_search_id", "search_results", ["search_id"])

    op.create_table(
        "sources",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "search_id",
            sa.String(36),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("reference", sa.String(32), nullable=False, unique=True),
        sa.Column("json_content", sa.JSON(), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_search_id", "reports", ["search_id"])

    op.create_table(
        "ai_summaries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "search_id",
            sa.String(36),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_summaries_search_id", "ai_summaries", ["search_id"])

    op.create_table(
        "risk_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "search_id",
            sa.String(36),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_scores_search_id", "risk_scores", ["search_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("search_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_search_id", "audit_logs", ["search_id"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    for table in (
        "audit_logs",
        "risk_scores",
        "ai_summaries",
        "reports",
        "sources",
        "search_results",
        "searches",
    ):
        op.drop_table(table)
