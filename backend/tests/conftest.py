"""Test configuration. Smoke tests need no database."""

import base64
import os

os.environ.setdefault("HOJE_ENV", "test")
os.environ.setdefault("HOJE_SECRET_KEY", base64.b64encode(bytes(32)).decode())
os.environ.setdefault("HOJE_DATABASE_URL", "postgresql+asyncpg://hoje:hoje@localhost:5432/hoje")
