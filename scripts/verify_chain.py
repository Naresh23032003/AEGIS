#!/usr/bin/env python3
"""Recomputes and checks one incident's hash chain against the stored rows.

Runs inside core-api (the only place with both `aegis` importable and
network access to aegis-db without publishing its port to the host, per
plan/04-security.md, Secrets and transport). Used by the e2e suite until
GET /incidents/{id}/verify-chain lands in phase 3 (PHASE_1_REPORT.md,
Deviations); `docker compose exec -T core-api python scripts/verify_chain.py <id>`.

Prints one JSON line: {"valid": bool, "break_at_seq": int | null}.
"""

from __future__ import annotations

import asyncio
import json
import sys

from aegis import db
from aegis.chain import next_hash
from aegis.events import format_ts


async def check(incident_id: str) -> dict[str, object]:
    async with db.connection() as conn:
        rows = await conn.fetch(
            "SELECT seq, event_id, type, actor, payload, prev_hash, hash, created_at "
            "FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq ASC",
            incident_id,
        )
    prev_hash = incident_id
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        envelope = {
            "id": row["event_id"],
            "ts": format_ts(row["created_at"]),
            "type": row["type"],
            "incident_id": incident_id,
            "actor": row["actor"],
            "payload": payload,
        }
        if row["prev_hash"] != prev_hash:
            return {"valid": False, "break_at_seq": row["seq"]}
        expected = next_hash(prev_hash, envelope)
        if expected != row["hash"]:
            return {"valid": False, "break_at_seq": row["seq"]}
        prev_hash = row["hash"]
    return {"valid": True, "break_at_seq": None}


async def main() -> None:
    incident_id = sys.argv[1]
    result = await check(incident_id)
    print(json.dumps(result))
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
