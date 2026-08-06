"""aegis.api: FastAPI app, REST + WebSocket fanout.

Phase 0 stub: only /healthz exists. Routes from plan/02-contracts.md,
HTTP API, arrive starting phase 1.
"""

from fastapi import FastAPI

app = FastAPI(title="aegis-core-api")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
