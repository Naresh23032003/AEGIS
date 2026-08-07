"""Evidence pack e2e. plan/phases/phase-6.md: "One e2e test downloads a
pack and asserts the PDF opens and the jsonl chain re-verifies."

Chain re-verification here is deliberately independent of the API's own
GET .../verify-chain endpoint: it recomputes aegis.chain.next_hash over the
downloaded events.jsonl lines by hand, so the test proves the pack is a
self-contained record rather than just re-asking the server to grade its
own homework.
"""

from __future__ import annotations

import io
import json
import time
import zipfile

import httpx
import pypdf
from aegis.chain import next_hash

from e2e.conftest import wait_for_incident, wait_for_resolution


def test_evidence_pack_downloads_and_chain_reverifies(client: httpx.Client) -> None:
    injected_at = time.time()
    client.post("/api/chaos/latency")
    try:
        incident = wait_for_incident(
            client, source_rule="latency_p95", service="target-orders", after=injected_at
        )
        resolved = wait_for_resolution(client, incident["id"])
    finally:
        client.delete("/api/chaos/latency")
    incident_id = resolved["id"]

    resp = client.get(f"/api/incidents/{incident_id}/evidence-pack")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert incident_id in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
        assert names == {"report.pdf", "events.jsonl"}, names
        pdf_bytes = zf.read("report.pdf")
        jsonl_bytes = zf.read("events.jsonl")

    # The PDF opens and contains the incident id somewhere in its text.
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert incident_id in full_text
    assert "Article 12" in full_text
    assert "Article 14" in full_text
    assert "Article 73" in full_text

    # The jsonl chain re-verifies independently of the server.
    lines = [json.loads(line) for line in jsonl_bytes.decode("utf-8").splitlines()]
    assert len(lines) > 0
    prev_hash = incident_id
    for line in lines:
        assert line["prev_hash"] == prev_hash
        envelope = {
            "id": line["id"],
            "ts": line["ts"],
            "type": line["type"],
            "incident_id": line["incident_id"],
            "actor": line["actor"],
            "payload": line["payload"],
        }
        assert next_hash(prev_hash, envelope) == line["hash"]
        prev_hash = line["hash"]

    # Cross-check against the live event log: same events, same order.
    events_resp = client.get(f"/api/incidents/{incident_id}/events")
    events_resp.raise_for_status()
    live_events = events_resp.json()
    assert [line["id"] for line in lines] == [e["id"] for e in live_events]
