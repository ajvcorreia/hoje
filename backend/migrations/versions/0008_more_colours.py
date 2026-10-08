"""categories.colour: 8 more palette colours (20 in total)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_COLOURS = (
    "slate",
    "red",
    "orange",
    "amber",
    "lime",
    "green",
    "teal",
    "cyan",
    "blue",
    "indigo",
    "violet",
    "pink",
)
NEW_COLOURS = ("rose", "fuchsia", "purple", "sky", "emerald", "yellow", "brown", "gray")


def _in_list(colours: tuple[str, ...]) -> str:
    return ",".join(f"'{c}'" for c in colours)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_categories_colour"), "categories", type_="check")
    op.create_check_constraint(
        op.f("ck_categories_colour"),
        "categories",
        f"colour in ({_in_list(OLD_COLOURS + NEW_COLOURS)})",
    )


def downgrade() -> None:
    # Remap the new colours first so restoring the narrower constraint cannot fail.
    op.execute(
        f"UPDATE categories SET colour = 'slate' WHERE colour in ({_in_list(NEW_COLOURS)})"  # noqa: S608
    )
    op.drop_constraint(op.f("ck_categories_colour"), "categories", type_="check")
    op.create_check_constraint(
        op.f("ck_categories_colour"), "categories", f"colour in ({_in_list(OLD_COLOURS)})"
    )
