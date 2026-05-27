"""T1 SNS — Meta(Facebook/Instagram) 채널 + 게시물 메트릭 시계열.

목적 (Priority 3 — 서울시 글로벌 SNS, Meta 우선):
- social_accounts: language(en/zh/ja) 는 003 에서 이미 존재 → client(VARCHAR(32)) 추가.
- social_posts: is_manual(수동 등록 플래그) 추가. (published_at=posted_at, title, content_type,
  url, external_id 는 003 에서 이미 존재.)
- social_post_metric_snapshots(신규): 게시물별 일/주 단위 메트릭 시계열.
  FALLBACK 모드(수동 콘텐츠)에서 조회수/도달/좋아요/댓글/공유를 누적 기록.

핵심 설계:
- (post_id, period, captured_at::date) UNIQUE → 같은 게시물·같은 주기·같은 날엔 1건만(멱등 재수집).
- views/reach/likes/comments/shares/engagement_total 은 BIGINT (대형 채널 누적 대비).
- raw(JSONB): Graph API 원본 응답 보존 → 매핑 변경에도 재처리 가능.

idempotent: ADD COLUMN IF NOT EXISTS / CREATE TABLE·INDEX IF NOT EXISTS
            (021 등 최근 마이그레이션 스타일과 일치).

Revision ID: 022
Revises: 021
Create Date: 2026-05-27
"""
from alembic import op


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # social_accounts — client 컬럼 (language 는 003 에 이미 존재)
    # ---------------------------------------------------------------------
    op.execute(
        "ALTER TABLE social_accounts ADD COLUMN IF NOT EXISTS client VARCHAR(32)"
    )

    # ---------------------------------------------------------------------
    # social_posts — 수동 등록 플래그 (FALLBACK 모드)
    # ---------------------------------------------------------------------
    op.execute(
        "ALTER TABLE social_posts "
        "ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT false"
    )

    # ---------------------------------------------------------------------
    # social_post_metric_snapshots — 게시물별 메트릭 시계열
    # ---------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS social_post_metric_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            period VARCHAR(8) NOT NULL,
            views BIGINT,
            reach BIGINT,
            likes BIGINT,
            comments BIGINT,
            shares BIGINT,
            engagement_total BIGINT,
            raw JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        )
        """
    )

    # post 별 조회 최적화.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_social_post_metric_snapshots_post_id "
        "ON social_post_metric_snapshots (post_id)"
    )

    # (post_id, period, captured_at::date) UNIQUE — 같은 게시물·주기·날짜엔 1건만.
    # captured_at 은 TIMESTAMPTZ 라 ::date 캐스트로 일 단위 멱등 보장.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_social_post_metric_snapshot_period_day "
        "ON social_post_metric_snapshots (post_id, period, (captured_at::date))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_social_post_metric_snapshot_period_day")
    op.execute("DROP INDEX IF EXISTS ix_social_post_metric_snapshots_post_id")
    op.execute("DROP TABLE IF EXISTS social_post_metric_snapshots")
    op.execute("ALTER TABLE social_posts DROP COLUMN IF EXISTS is_manual")
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS client")
