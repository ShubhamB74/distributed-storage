import uuid
from datetime import datetime

from pydantic import BaseModel


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    is_current: bool
