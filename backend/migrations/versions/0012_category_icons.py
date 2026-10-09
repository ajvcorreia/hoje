"""users.show_category_icons: show the category glyphs in the calendar, per user

Also gives the bundled default categories their glyph where the user has not set one.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ICONS = {
    "Vacation": "🏖️",
    "Holidays": "🎉",
    "Important": "❗",
    "Events": "📅",
    "Visits": "👥",
    "Flights": "✈️",
    "Finance": "💰",
}


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "show_category_icons", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    categories = sa.table("categories", sa.column("name", sa.String), sa.column("icon", sa.String))
    for name, icon in DEFAULT_ICONS.items():
        op.execute(
            categories.update()
            .where(categories.c.name == name, categories.c.icon.is_(None))
            .values(icon=icon)
        )


def downgrade() -> None:
    op.drop_column("users", "show_category_icons")
