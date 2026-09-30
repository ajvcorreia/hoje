"""Reusable annotated column types for the models."""

import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import func
from sqlalchemy.orm import mapped_column

UuidPk = Annotated[
    uuid.UUID,
    mapped_column(primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()),
]
CreatedAt = Annotated[datetime, mapped_column(server_default=func.now())]
UpdatedAt = Annotated[datetime, mapped_column(server_default=func.now(), onupdate=func.now())]
