"""event_invites.email and status are text, as the model declares them (0017 made them varchar)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("event_invites", "email", type_=sa.Text(), existing_nullable=False)
    op.alter_column("event_invites", "status", type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("event_invites", "status", type_=sa.String(), existing_nullable=False)
    op.alter_column("event_invites", "email", type_=sa.String(), existing_nullable=False)
