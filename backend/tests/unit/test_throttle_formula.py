import pytest

from hoje.services.throttle import lockout_seconds


@pytest.mark.parametrize(
    ("failures", "seconds"),
    [
        (0, 0),
        (4, 0),
        (5, 60),
        (6, 120),
        (7, 240),
        (8, 480),
        (9, 960),
        (10, 1920),
        (11, 3600),
        (12, 3600),
        (1000, 3600),
    ],
)
def test_lockout_seconds(failures: int, seconds: int) -> None:
    assert lockout_seconds(failures) == seconds
