"""Background worker (reminder delivery is added in a later phase)."""

import os
from pathlib import Path

HEARTBEAT_PATH = Path(os.environ.get("HOJE_WORKER_HEARTBEAT_FILE", "/tmp/hoje-worker-heartbeat"))  # noqa: S108
