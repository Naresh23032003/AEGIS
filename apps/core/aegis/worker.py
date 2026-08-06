"""aegis.worker: detection loop, LangGraph agent runs, supervisor.

Phase 1: the deterministic detection loop only. Agent runs and the
supervisor arrive in phase 2 (plan/03-agents-and-policy.md).
"""

import asyncio
import logging
import signal

from aegis import db
from aegis.detection import run_detection_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
logger = logging.getLogger("aegis.worker")


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    await db.init_schema()
    logger.info("worker started, detection loop polling every 5s")
    try:
        await run_detection_loop(stop)
    finally:
        await db.close_pool()
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
