"""rbac department/role constraints

Revision ID: 002
Revises: 001
Create Date: 2026-04-28
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    # Backfill: normalize role + map old free-text departments to enum values.
    # - role=admin stays admin; everything else becomes member
    # - old role=accountant gets dept=finance (재무팀)
    # - everyone else without a recognized dept lands in 'admin' (관리자) and is dashboard-only by default
    # NOTE: This backfill is irreversible. Original free-text department/role values are overwritten.
    op.execute(
        """
        UPDATE users
        SET department = CASE
            WHEN department IN ('marketing_1','marketing_2','new_business','finance','new_media','design','admin') THEN department
            WHEN role = 'accountant' THEN 'finance'
            ELSE 'admin'
        END,
        role = CASE
            WHEN role = 'admin' THEN 'admin'
            ELSE 'member'
        END
        """
    )

    op.alter_column("users", "department", nullable=False)
    op.create_check_constraint(
        "users_department_check",
        "users",
        "department IN ('marketing_1','marketing_2','new_business','finance','new_media','design','admin')",
    )
    op.create_check_constraint(
        "users_role_check",
        "users",
        "role IN ('admin','member')",
    )


def downgrade():
    op.drop_constraint("users_role_check", "users")
    op.drop_constraint("users_department_check", "users")
    op.alter_column("users", "department", nullable=True)
