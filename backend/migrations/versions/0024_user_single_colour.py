"""users.single_colour(_value): draw every event in one colour instead of its category's

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLOURS = (
    "slate", "red", "orange", "amber", "lime", "green", "teal", "cyan", "blue", "indigo",
    "violet", "pink", "rose", "fuchsia", "purple", "sky", "emerald", "yellow", "brown", "gray",
)  # fmt: skip
_COLOUR_LIST = ",".join(f"'{c}'" for c in _COLOURS)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("single_colour", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "single_colour_value", sa.Text(), server_default=sa.text("'blue'"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_single_colour_value"),
        "users",
        f"single_colour_value in ({_COLOUR_LIST}) or single_colour_value ~ '^#[0-9a-f]{{6}}$'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_single_colour_value"), "users", type_="check")
    op.drop_column("users", "single_colour_value")
    op.drop_column("users", "single_colour")
