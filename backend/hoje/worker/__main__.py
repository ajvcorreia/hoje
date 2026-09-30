"""Worker entrypoint: ``python -m hoje.worker``. Currently a heartbeat-only stub."""

import asyncio
import contextlib
import signal

from hoje.config import get_settings
from hoje.logging import configure_logging, get_logger
from hoje.worker import HEARTBEAT_PATH

log = get_logger("hoje.worker")


def touch_heartbeat() -> None:
    HEARTBEAT_PATH.touch()


async def run(interval: float, stop: asyncio.Event) -> None:
    log.info("worker_started", interval_seconds=interval)
    while not stop.is_set():
        touch_heartbeat()
        log.info("worker_heartbeat")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    log.info("worker_stopped")


async def amain() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await run(settings.worker_interval_seconds, stop)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
