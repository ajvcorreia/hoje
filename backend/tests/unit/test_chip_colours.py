"""Daily summary chips for custom category colours."""

import pytest

from hoje.services.daily_summary import _CHIP, _contrast, chip_colours


def _rgb(value: str) -> tuple[float, float, float]:
    return tuple(float(int(value[i : i + 2], 16)) for i in (1, 3, 5))  # type: ignore[return-value]


def test_palette_names_keep_their_palette_chip():
    assert chip_colours("red") == _CHIP["red"]


@pytest.mark.parametrize(
    "colour", ["#ffff00", "#000000", "#ffffff", "#2f6fdf", "#d98a1c", "#00ff7f"]
)
def test_a_custom_colour_gives_a_readable_chip(colour):
    fill, text = chip_colours(colour)

    assert _contrast(_rgb(text), _rgb(fill)) >= 4.5


def test_an_unknown_value_falls_back_to_slate():
    assert chip_colours("mauve") == _CHIP["slate"]
