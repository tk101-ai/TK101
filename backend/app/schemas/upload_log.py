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

    model_config = {"from_attributes": True}
