"""users.weekend_shade: how strongly weekends and days off are shaded

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("weekend_shade", sa.Text(), server_default=sa.text("'subtle'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_users_weekend_shade"),
        "users",
        "weekend_shade in ('subtle', 'medium', 'strong', 'bold')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_weekend_shade"), "users", type_="check")
    op.drop_column("users", "weekend_shade")
