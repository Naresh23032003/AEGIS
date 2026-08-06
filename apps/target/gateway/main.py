"""target-gateway: public API of the demo system.

Phase 0 stub: only /healthz. Real endpoints (create order -> payment -> db
write through Toxiproxy) arrive in phase 1, plan/06-milestones.md.
"""

from fastapi import FastAPI

app = FastAPI(title="target-gateway")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
