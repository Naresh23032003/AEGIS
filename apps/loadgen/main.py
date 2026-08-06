"""loadgen: constant realistic traffic against target-gateway.

~5 rps, jittered, mixed between checkout (writes) and order lookups
(reads, cache hits on repeat) so target-orders exercises both the DB path
through Toxiproxy and the redis cache path. plan/06-milestones.md, Phase 1.
"""

import asyncio
import logging
import os
import random

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s loadgen %(message)s")
logger = logging.getLogger("loadgen")

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://target-gateway:9000")
TARGET_RPS = 5.0
SKUS = ["widget-a", "widget-b", "gadget-c", "gizmo-d", "thing-e"]

recent_order_ids: list[str] = []


async def do_checkout(client: httpx.AsyncClient) -> None:
    sku = random.choice(SKUS)  # noqa: S311 traffic shaping, not crypto
    qty = random.randint(1, 5)  # noqa: S311 traffic shaping, not crypto
    amount = round(qty * random.uniform(5.0, 40.0), 2)  # noqa: S311 traffic shaping, not crypto
    try:
        resp = await client.post(
            f"{GATEWAY_URL}/checkout", json={"sku": sku, "qty": qty, "amount": amount}
        )
        if resp.status_code == 200:
            order = resp.json()
            recent_order_ids.append(order["id"])
            recent_order_ids[:] = recent_order_ids[-50:]
        else:
            logger.info("checkout non-200: %s", resp.status_code)
    except httpx.HTTPError as exc:
        logger.info("checkout failed: %s", exc)


async def do_lookup(client: httpx.AsyncClient) -> None:
    if not recent_order_ids:
        return
    order_id = random.choice(recent_order_ids)  # noqa: S311 traffic shaping, not crypto
    try:
        resp = await client.get(f"{GATEWAY_URL}/orders/{order_id}")
        if resp.status_code not in (200, 404):
            logger.info("lookup non-200: %s", resp.status_code)
    except httpx.HTTPError as exc:
        logger.info("lookup failed: %s", exc)


async def main() -> None:
    logger.info("loadgen started, ~%s rps against %s", TARGET_RPS, GATEWAY_URL)
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            if random.random() < 0.2 and recent_order_ids:  # noqa: S311 traffic shaping
                await do_lookup(client)
            else:
                await do_checkout(client)
            jitter = random.uniform(0.7, 1.3)  # noqa: S311 traffic shaping, not crypto
            await asyncio.sleep((1.0 / TARGET_RPS) * jitter)


if __name__ == "__main__":
    asyncio.run(main())
