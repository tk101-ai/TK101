"""sns tables (social accounts, weekly snapshots, posts)

Revision ID: 003
Revises: 002
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    # social_accounts: one row per (platform, language) channel.
    # Simplified UNIQUE on (platform, language) since handle is nullable.
    op.create_table(
        "social_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("platform", sa.String, nullable=False),
        sa.Column("language", sa.String, nullable=False),
        sa.Column("handle", sa.String, nullable=True),
        sa.Column("page_url", sa.String, nullable=True),
        sa.Column("external_id", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("extra_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("platform", "language", name="social_accounts_platform_language_key"),
        sa.CheckConstraint(
            "platform IN ('facebook','instagram','twitter','youtube','weibo')",
            name="social_accounts_platform_check",
        ),
        sa.CheckConstraint(
            "language IN ('en','zh','ja')",
            name="social_accounts_language_check",
        ),
    )

    # social_weekly_snapshots: weekly follower counts per account.
    op.create_table(
        "social_weekly_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("social_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("week_number", sa.Integer, nullable=False),
        sa.Column("followers", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "account_id", "year", "month", "week_number",
            name="social_weekly_snapshots_account_period_key",
        ),
        sa.CheckConstraint(
            "week_number BETWEEN 1 AND 5",
            name="social_weekly_snapshots_week_number_check",
        ),
        sa.CheckConstraint(
            "month BETWEEN 1 AND 12",
            name="social_weekly_snapshots_month_check",
        ),
    )

    # social_posts: individual post metrics per account.
    op.create_table(
        "social_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("social_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("posted_at", sa.Date, nullable=False),
        sa.Column("title", sa.String, nullable=True),
        sa.Column("content_type", sa.String, nullable=True),
        sa.Column("producer", sa.String, nullable=True),
        sa.Column("view_count", sa.Integer, nullable=True),
        sa.Column("reach_count", sa.Integer, nullable=True),
        sa.Column("comment_count", sa.Integer, nullable=True),
        sa.Column("like_count", sa.Integer, nullable=True),
        sa.Column("share_count", sa.Integer, nullable=True),
        sa.Column("save_count", sa.Integer, nullable=True),
        sa.Column("repost_count", sa.Integer, nullable=True),
        sa.Column("total_engagement", sa.Integer, nullable=True),
        sa.Column("url", sa.String, nullable=True),
        sa.Column("data_recorded_at", sa.Date, nullable=True),
        sa.Column("external_id", sa.String, nullable=True, index=True),
        sa.Column("extra_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # Partial unique index: dedupe by external_id when present (e.g., YouTube videoId).
    op.create_index(
        "social_posts_account_external_uniq",
        "social_posts",
        ["account_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("social_posts_account_external_uniq", table_name="social_posts")
    op.drop_table("social_posts")
    op.drop_table("social_weekly_snapshots")
    op.drop_table("social_accounts")
