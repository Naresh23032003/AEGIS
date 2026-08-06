"""loadgen: constant realistic traffic against target-gateway.

Phase 0 stub: sleeps and logs. Real mixed traffic at ~5 rps arrives in
phase 1, plan/06-milestones.md.
"""

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s loadgen %(message)s")
logger = logging.getLogger("loadgen")

if __name__ == "__main__":
    logger.info("loadgen stub started, no traffic generation yet (phase 0)")
    while True:
        time.sleep(10)
        logger.info("heartbeat")
