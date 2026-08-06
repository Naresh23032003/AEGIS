"""aegis.worker: detection loop, LangGraph agent runs, supervisor.

Phase 0 stub: an asyncio loop that logs a heartbeat and exits cleanly on
SIGTERM. Detection rules, incident creation, and the agent graph arrive
starting phase 1 and phase 2 (plan/03-agents-and-policy.md).
"""

import asyncio
import logging
import signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
logger = logging.getLogger("aegis.worker")


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("worker stub started, no detection loop yet (phase 0)")
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            logger.info("heartbeat")
    logger.info("worker stub stopped")


if __name__ == "__main__":
    asyncio.run(main())
