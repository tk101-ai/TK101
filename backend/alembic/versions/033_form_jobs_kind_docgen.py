"""form_jobs 일반화 — docgen 잡 영속화용 kind/source_mode (PR-E #1).

form_jobs 를 fill(양식 작성)/generate(문서 생성) 두 종류로 일반화한다.
- kind: 신규 PG ENUM form_job_kind('fill','generate'), NOT NULL, server_default='fill'.
  ADD COLUMN 시점에 기존 row 가 'fill' 로 원자적 backfill 되어 별도 UPDATE 불필요.
  005 의 ENUM(create_type=False) + .create(checkfirst=True) 관용구를 그대로 사용.
- source_mode: TEXT NULL (rag/uploaded/both; fill 잡은 NULL). 두 번째 enum 회피.
- 인덱스: ix_form_jobs_kind, (kind, created_at DESC) — 관리자 토큰/비용 집계용.

status(form_job_status) enum 에는 값 추가하지 않는다(R-ENUM): generate 잡은
성공 시 completed, 실패 시 failed 만 재사용한다.

Revision ID: 033
Revises: 032
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


FORM_JOB_KIND_NAME = "form_job_kind"
FORM_JOB_KIND_VALUES = ("fill", "generate")


def upgrade():
    bind = op.get_bind()
    # 1. 신규 enum 생성. create_type=False 컬럼과 분리 생성(005 관용구).
    ENUM(*FORM_JOB_KIND_VALUES, name=FORM_JOB_KIND_NAME).create(bind, checkfirst=True)

    form_job_kind = ENUM(
        *FORM_JOB_KIND_VALUES, name=FORM_JOB_KIND_NAME, create_type=False
    )

    # 2. kind 컬럼: NOT NULL + server_default 'fill' → 기존 row 원자적 backfill.
    op.add_column(
        "form_jobs",
        sa.Column(
            "kind",
            form_job_kind,
            nullable=False,
            server_default="fill",
        ),
    )
    # 3. source_mode 컬럼: rag/uploaded/both (fill 잡은 null).
    op.add_column(
        "form_jobs",
        sa.Column("source_mode", sa.Text, nullable=True),
    )

    # 4. 관리자 집계 인덱스.
    op.create_index("ix_form_jobs_kind", "form_jobs", ["kind"])
    op.execute(
        "CREATE INDEX ix_form_jobs_kind_created_at_desc "
        "ON form_jobs (kind, created_at DESC)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_form_jobs_kind_created_at_desc")
    op.drop_index("ix_form_jobs_kind", table_name="form_jobs")
    op.drop_column("form_jobs", "source_mode")
    op.drop_column("form_jobs", "kind")

    bind = op.get_bind()
    ENUM(name=FORM_JOB_KIND_NAME).drop(bind, checkfirst=True)
