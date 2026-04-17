"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String, unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("department", sa.String, nullable=True),
        sa.Column("role", sa.String, nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bank_name", sa.String, nullable=False),
        sa.Column("account_number", sa.String, unique=True, nullable=False),
        sa.Column("account_holder", sa.String, nullable=False),
        sa.Column("business_registration_no", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "upload_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("upload_type", sa.String, nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("row_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("error_detail", JSONB, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="processing"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("counterpart_name", sa.String, nullable=True),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("transaction_type", sa.String, nullable=False),
        sa.Column("matched_transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("match_status", sa.String, server_default="unmatched"),
        sa.Column("memo", sa.Text, nullable=True),
        sa.Column("upload_log_id", UUID(as_uuid=True), sa.ForeignKey("upload_logs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "tax_invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_type", sa.String, nullable=False),
        sa.Column("invoice_number", sa.String, unique=True, nullable=True),
        sa.Column("issue_date", sa.Date, nullable=False),
        sa.Column("supplier_name", sa.String, nullable=False),
        sa.Column("supplier_biz_no", sa.String, nullable=True),
        sa.Column("buyer_name", sa.String, nullable=True),
        sa.Column("buyer_biz_no", sa.String, nullable=True),
        sa.Column("supply_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("matched_transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("match_status", sa.String, server_default="unmatched"),
        sa.Column("memo", sa.Text, nullable=True),
        sa.Column("upload_log_id", UUID(as_uuid=True), sa.ForeignKey("upload_logs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # Create admin seed user (password: admin123 - must change on first login)
    op.execute("""
        INSERT INTO users (id, email, hashed_password, name, department, role)
        VALUES (
            gen_random_uuid(),
            'admin@tk101.co.kr',
            '$2b$12$LJ3m4ys3Lk0TSwHjlT3Xb.7WtXH9aZPeyVb0wQf2SQIG/xcURwmu',
            '관리자',
            '경영',
            'admin'
        )
        ON CONFLICT (email) DO NOTHING;
    """)


def downgrade():
    op.drop_table("tax_invoices")
    op.drop_table("transactions")
    op.drop_table("upload_logs")
    op.drop_table("accounts")
    op.drop_table("users")
