"""categories.colour: a palette name or any custom #rrggbb colour

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op

from hoje.constants import COLOURS

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PALETTE = ",".join(f"'{c}'" for c in COLOURS)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_categories_colour"), "categories", type_="check")
    op.create_check_constraint(
        op.f("ck_categories_colour"),
        "categories",
        f"colour in ({PALETTE}) or colour ~ '^#[0-9a-f]{{6}}$'",
    )


def downgrade() -> None:
    # A custom colour cannot exist under the narrower constraint: fall back to grey.
    op.execute("UPDATE categories SET colour = 'gray' WHERE colour LIKE '#%'")
    op.drop_constraint(op.f("ck_categories_colour"), "categories", type_="check")
    op.create_check_constraint(op.f("ck_categories_colour"), "categories", f"colour in ({PALETTE})")
