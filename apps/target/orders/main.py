"""target-orders: talks to shop Postgres through Toxiproxy.

Phase 0 stub: only /healthz. Real DB-backed endpoints arrive in phase 1,
plan/06-milestones.md.
"""

from fastapi import FastAPI

app = FastAPI(title="target-orders")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
