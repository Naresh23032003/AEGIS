"""target-orders: talks to shop Postgres through Toxiproxy, caches reads
through shop-redis. plan/06-milestones.md, Phase 1.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import asyncpg
import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s orders %(message)s")
logger = logging.getLogger("target.orders")

SHOP_DATABASE_URL = os.environ["SHOP_DATABASE_URL"]
SHOP_REDIS_URL = os.environ["SHOP_REDIS_URL"]
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4318")
TOXIPROXY_URL = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474")
CACHE_TTL_SECONDS = 30
SHOPDB_PROXY = {"name": "shopdb", "listen": "0.0.0.0:5432", "upstream": "shop-db:5432"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id text PRIMARY KEY,
    sku text NOT NULL,
    qty integer NOT NULL,
    status text NOT NULL DEFAULT 'created',
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


def setup_otel(service_name: str) -> None:
    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{OTEL_ENDPOINT}/v1/metrics"), export_interval_millis=5000
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))


setup_otel("target-orders")
AsyncPGInstrumentor().instrument()
RedisInstrumentor().instrument()

pool: asyncpg.Pool | None = None
cache: redis.Redis | None = None


async def ensure_toxiproxy_proxy() -> None:
    """Create the orders -> shop-db proxy on toxiproxy if it does not exist
    yet. Idempotent: a 409 means another orders instance beat us to it.
    plan/01-architecture.md: orders reaches shop-db only through Toxiproxy.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(10):
            try:
                resp = await client.post(f"{TOXIPROXY_URL}/proxies", json=SHOPDB_PROXY)
                if resp.status_code in (200, 201, 409):
                    return
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("toxiproxy not ready yet (attempt %d): %s", attempt, exc)
                await asyncio.sleep(1)
    raise RuntimeError("could not create toxiproxy shopdb proxy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, cache
    await ensure_toxiproxy_proxy()
    pool = await asyncpg.create_pool(SHOP_DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    cache = redis.from_url(SHOP_REDIS_URL, decode_responses=True)
    yield
    await pool.close()
    await cache.aclose()


app = FastAPI(title="target-orders", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


class CreateOrder(BaseModel):
    sku: str
    qty: int


class CompleteOrder(BaseModel):
    status: str


def _cache_key(order_id: str) -> str:
    return f"order:{order_id}"


async def _row_to_dict(row: asyncpg.Record) -> dict:
    return {
        "id": row["id"],
        "sku": row["sku"],
        "qty": row["qty"],
        "status": row["status"],
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/orders")
async def create_order(req: CreateOrder) -> dict:
    assert pool is not None and cache is not None
    order_id = f"ord_{os.urandom(6).hex()}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO orders (id, sku, qty, status) VALUES ($1, $2, $3, 'created')",
            order_id,
            req.sku,
            req.qty,
        )
    order = {"id": order_id, "sku": req.sku, "qty": req.qty, "status": "created"}
    await cache.set(_cache_key(order_id), json.dumps(order), ex=CACHE_TTL_SECONDS)
    return order


@app.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict:
    assert pool is not None and cache is not None
    cached = await cache.get(_cache_key(order_id))
    if cached is not None:
        result: dict = json.loads(cached)
        return result

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, sku, qty, status FROM orders WHERE id = $1", order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    order = await _row_to_dict(row)
    await cache.set(_cache_key(order_id), json.dumps(order), ex=CACHE_TTL_SECONDS)
    return order


@app.post("/orders/{order_id}/complete")
async def complete_order(order_id: str, req: CompleteOrder) -> dict:
    assert pool is not None and cache is not None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE orders SET status = $1 WHERE id = $2 RETURNING id, sku, qty, status",
            req.status,
            order_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    order = await _row_to_dict(row)
    await cache.set(_cache_key(order_id), json.dumps(order), ex=CACHE_TTL_SECONDS)
    return order
