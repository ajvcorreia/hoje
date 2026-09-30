"""Hoje - self-hosted personal planner."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hoje")
except PackageNotFoundError:  # pragma: no cover - running from a bare checkout
    __version__ = "0.0.0"
