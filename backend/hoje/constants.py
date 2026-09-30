"""Shared constants: the fixed category colour palette."""

from typing import Literal, get_args

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
]

COLOURS: tuple[str, ...] = get_args(Colour)
