"""Container healthcheck: ``python -m hoje.worker.healthcheck``.

Exits 0 if the heartbeat file is younger than 3 x HOJE_WORKER_INTERVAL_SECONDS, else 1.
"""

import os
import sys
import time

from hoje.worker import HEARTBEAT_PATH


def is_healthy(now: float | None = None) -> bool:
    interval = float(os.environ.get("HOJE_WORKER_INTERVAL_SECONDS") or 60)
    try:
        age = (time.time() if now is None else now) - HEARTBEAT_PATH.stat().st_mtime
    except OSError:
        return False
    return age < 3 * interval


def main() -> None:
    sys.exit(0 if is_healthy() else 1)


if __name__ == "__main__":
    main()
