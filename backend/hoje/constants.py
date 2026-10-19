"""Shared constants: the category colour palette and what a category colour may be."""

import re
from typing import Annotated, Literal, get_args

from pydantic import AfterValidator, Field

Colour = Literal[
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
    "rose",
    "fuchsia",
    "purple",
    "sky",
    "emerald",
    "yellow",
    "brown",
    "gray",
]

COLOURS: tuple[str, ...] = get_args(Colour)

HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _category_colour(value: str) -> str:
    """A palette name, or a custom ``#rrggbb`` colour (stored lower-case)."""
    if value in COLOURS:
        return value
    if HEX_COLOUR.match(value):
        return value.lower()
    raise ValueError("colour must be a palette name or a #rrggbb value")


# What a category may carry: one of the named palette colours, or any #rrggbb colour.
CategoryColour = Annotated[
    str,
    AfterValidator(_category_colour),
    Field(description="A palette colour name, or a custom colour as #rrggbb."),
]
