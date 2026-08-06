"""target-gateway: public API of the demo system.

Fronts orders and payments. loadgen drives traffic against this service
only; gateway fans the call chain out to the internal services.
plan/06-milestones.md, Phase 1.
"""

import logging
import os

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s gateway %(message)s")
logger = logging.getLogger("target.gateway")

ORDERS_URL = os.environ.get("ORDERS_URL", "http://target-orders:9001")
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://target-payments:9002")
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4318")


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


setup_otel("target-gateway")

app = FastAPI(title="target-gateway")
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

client = httpx.AsyncClient(timeout=5.0)


class CheckoutRequest(BaseModel):
    sku: str
    qty: int
    amount: float


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/checkout")
async def checkout(req: CheckoutRequest) -> dict:
    order_resp = await client.post(
        f"{ORDERS_URL}/orders", json={"sku": req.sku, "qty": req.qty}
    )
    order_resp.raise_for_status()
    order = order_resp.json()

    try:
        charge_resp = await client.post(
            f"{PAYMENTS_URL}/charge", json={"order_id": order["id"], "amount": req.amount}
        )
        charge_resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("payment failed for order %s: %s", order["id"], exc)
        await client.post(f"{ORDERS_URL}/orders/{order['id']}/complete", json={"status": "failed"})
        raise HTTPException(status_code=502, detail="payment failed") from exc

    complete_resp = await client.post(
        f"{ORDERS_URL}/orders/{order['id']}/complete", json={"status": "paid"}
    )
    complete_resp.raise_for_status()
    return complete_resp.json()


@app.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict:
    resp = await client.get(f"{ORDERS_URL}/orders/{order_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="order not found")
    resp.raise_for_status()
    return resp.json()
