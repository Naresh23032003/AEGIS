"""aegis.executor: the only process allowed to touch the Docker socket.

Phase 0 stub: an asyncio loop that logs a heartbeat and exits cleanly on
SIGTERM. The allowlisted action catalog and Docker socket RPC arrive in
phase 2 (plan/04-security.md, Executor sandbox). No shell=True, ever.
"""

import asyncio
import logging
import signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s executor %(message)s")
logger = logging.getLogger("aegis.executor")


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("executor stub started, no action catalog yet (phase 0)")
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            logger.info("heartbeat")
    logger.info("executor stub stopped")


if __name__ == "__main__":
    asyncio.run(main())
