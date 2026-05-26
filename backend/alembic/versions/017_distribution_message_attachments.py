"""T9 distribution_messages 에 파일 첨부 컬럼 5종 추가.

목적 (T9 — 2026-05-26):
- 텔레그램 자동화 메시지에 이미지·문서(PDF/엑셀/한글) 첨부 지원.
- 검수 UI 에서 사람이 메시지 카드마다 파일을 업로드 → NAS RW 저장 → 송신 시
  Telethon ``client.send_file(path, caption=..., force_document=...)`` 분기.

컬럼:
- attachment_path     : NAS RW 절대경로 (`/mnt/nas-rw/distribution/{session_id}/{message_id}.{ext}`)
- attachment_filename : 사용자 원본 파일명 (UI 표시 + 송신 시 attribute filename)
- attachment_mime     : MIME 타입 (송신 force_document 판단)
- attachment_kind     : 'image' / 'document'  (UI 미리보기 분기)
- attachment_caption  : 첨부에만 붙는 캡션 (없으면 content 사용)

idempotent:
- 모든 ADD COLUMN 에 IF NOT EXISTS. 부분 실패 후 재실행 안전.
"""
from alembic import op


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS attachment_path VARCHAR(700) NULL"
    )
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(300) NULL"
    )
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS attachment_mime VARCHAR(150) NULL"
    )
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS attachment_kind VARCHAR(20) NULL"
    )
    op.execute(
        "ALTER TABLE distribution_messages "
        "ADD COLUMN IF NOT EXISTS attachment_caption TEXT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS attachment_caption"
    )
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS attachment_kind"
    )
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS attachment_mime"
    )
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS attachment_filename"
    )
    op.execute(
        "ALTER TABLE distribution_messages DROP COLUMN IF EXISTS attachment_path"
    )
