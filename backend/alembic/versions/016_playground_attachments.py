"""Playground 첨부 파일 테이블 추가.

목적 (T8 Phase 6 — 2026-05-20):
- LLM 채팅 입력에 파일(이미지/PDF/텍스트) 첨부 지원.
- 업로드 → playground_attachments row → /chat 호출 시 attachment_ids 로 참조.
- 이미지: vision-capable 모델만 LLM payload 에 data URL 로 동봉.
- PDF/텍스트: 백엔드에서 텍스트 추출 후 사용자 메시지 본문 앞에 inline.

저장:
- 실파일은 ``{playground_media_root}/{department}/{user_id}/attachments/{file_id}.{ext}``.
- DB 는 메타 + 텍스트 추출본(PDF/text) 만 보관. 이미지 본문은 디스크 + 다운로드 endpoint.

idempotent:
- ``CREATE TABLE IF NOT EXISTS``. 부분 실패 후 재실행 안전.
"""
from alembic import op


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS playground_attachments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id UUID NULL REFERENCES playground_sessions(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL,
            filename VARCHAR(300) NOT NULL,
            mime VARCHAR(150) NOT NULL,
            size_bytes BIGINT NOT NULL,
            file_path VARCHAR(700) NOT NULL,
            extracted_text TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_playground_attachments_user "
        "ON playground_attachments(user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_playground_attachments_session "
        "ON playground_attachments(session_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_playground_attachments_session")
    op.execute("DROP INDEX IF EXISTS idx_playground_attachments_user")
    op.execute("DROP TABLE IF EXISTS playground_attachments")
