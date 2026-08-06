"""target-payments: has fault endpoints (memory leak, error spike).

Phase 0 stub: only /healthz. Fault hooks (error_spike flag file,
memory_leak endpoint) arrive in phase 1, plan/06-milestones.md.
"""

from fastapi import FastAPI

app = FastAPI(title="target-payments")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
