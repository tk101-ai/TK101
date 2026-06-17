"""RBAC 확장 — 다중부서 + 부서·모듈 grant 테이블 + 사용자 승인 status (2026-06-17).

1. users.status 추가 (pending/active/rejected). 기존 사용자는 active 백필.
2. user_departments (사용자 다대다 부서). 기존 users.department 를 주 부서로 시드.
3. department_module_grants (부서→모듈 grant). 현 하드코딩 매핑을 시드로 INSERT
   → 동작 100% 보존, 이후 관리자가 런타임 편집.

자기완결형: app 코드 import 없이 매핑을 인라인 스냅샷으로 보관.

Revision ID: 031
Revises: 030
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None

# 현 registry.DEPARTMENT_MODULES 스냅샷 (시드).
_DEPARTMENT_MODULES: dict[str, list[str]] = {
    "admin": ["dashboard", "nas_search", "form_filler", "playground", "distribution"],
    "finance": ["dashboard", "finance", "nas_search", "form_filler", "playground"],
    "marketing_1": ["dashboard", "marketing_sns", "nas_search", "form_filler",
                    "review_translation", "playground"],
    "marketing_2": ["dashboard", "nas_search", "form_filler", "playground"],
    "new_business": ["dashboard", "nas_search", "form_filler", "distribution", "playground"],
    "new_media": ["dashboard", "nas_search", "form_filler", "playground"],
    "design": ["dashboard", "nas_search", "form_filler", "playground"],
}


def upgrade() -> None:
    # 1) users.status
    op.add_column(
        "users",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "users_status_check", "users",
        "status IN ('pending','active','rejected')",
    )

    # 2) user_departments
    op.create_table(
        "user_departments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "department", name="uq_user_department"),
    )
    op.create_index("ix_user_departments_user_id", "user_departments", ["user_id"])
    # 기존 사용자의 주 부서를 user_departments 로 시드.
    op.execute(
        "INSERT INTO user_departments (id, user_id, department, created_at) "
        "SELECT gen_random_uuid(), id, department, now() FROM users "
        "WHERE department IS NOT NULL "
        "ON CONFLICT (user_id, department) DO NOTHING"
    )

    # 3) department_module_grants
    op.create_table(
        "department_module_grants",
        sa.Column("department", sa.String(), primary_key=True),
        sa.Column("module", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    ins = sa.text(
        "INSERT INTO department_module_grants (department, module) "
        "VALUES (:d, :m) ON CONFLICT DO NOTHING"
    )
    for dept, mods in _DEPARTMENT_MODULES.items():
        for m in mods:
            bind.execute(ins, {"d": dept, "m": m})


def downgrade() -> None:
    op.drop_table("department_module_grants")
    op.drop_index("ix_user_departments_user_id", table_name="user_departments")
    op.drop_table("user_departments")
    op.drop_constraint("users_status_check", "users", type_="check")
    op.drop_column("users", "status")
