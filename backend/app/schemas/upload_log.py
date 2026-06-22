import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadLogRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    upload_type: str
    account_id: uuid.UUID | None
    row_count: int
    error_count: int
    status: str
    created_at: datetime
    # 마이그레이션 007 통계 메타 (모델과 동일). /api/upload-history 와 동일 통계 노출.
    duplicate_count: int = 0
    imported_count: int = 0
    bank_key: str | None = None
    period_label: str | None = None

    model_config = {"from_attributes": True}
