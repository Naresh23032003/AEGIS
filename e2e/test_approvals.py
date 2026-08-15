"""Signed approvals and vetoes. plan/06-milestones.md, Phase 3 acceptance:
"a red-tier action visibly parks until an approval signed by a registered
key arrives (integration test signs with PyNaCl)"; "tampering with a stored
event makes verify-chain report the break."

The red-tier flow is seeded rather than driven through a live chaos
scenario: none of the five scenarios' expected fix paths is a red action
(flush_queue and restart_database are not any scenario's answer, by
design, per plan/03's chaos scenario table), so nothing here would ever
naturally propose one. scripts/seed_red_action.py runs a single-node graph
(just gate) inside core-worker to get a real LangGraph interrupt() pause,
then this test drives the rest (POST /keys, POST /approvals) exactly as a
human approver would, over the real HTTP API, with a real Ed25519
signature. Once approved, aegis.worker's own approval dispatch loop (a
different process from this test, from core-api, and from the process
that originally paused) wakes the run on its own; this test only proves
that happened by polling the incident, the same way test_scenarios.py does.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import nacl.signing

from e2e.conftest import events_for, verify_chain, wait_for_resolution

COMPOSE = ["docker", "compose", "-f", "deploy/docker-compose.yml"]
SEED_SCRIPT = Path(__file__).parent.parent / "scripts" / "seed_red_action.py"
YELLOW_SEED_SCRIPT = Path(__file__).parent.parent / "scripts" / "seed_yellow_action.py"


def _seed_parked_red_action() -> tuple[str, str]:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, internal test tooling
        [*COMPOSE, "exec", "-T", "core-worker", "python", "-"],  # noqa: S607
        input=SEED_SCRIPT.read_text(),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    seeded = json.loads(proc.stdout.strip().splitlines()[-1])
    return seeded["incident_id"], seeded["action_id"]


def _register_key() -> tuple[nacl.signing.SigningKey, str]:
    key = nacl.signing.SigningKey.generate()
    pubkey_hex = bytes(key.verify_key).hex()
    return key, pubkey_hex


def _sign(
    key: nacl.signing.SigningKey, *, action_id: str, decision: str, ts: str | None = None
) -> dict[str, str]:
    ts = ts or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"
    payload = json.dumps(
        {"action_id": action_id, "decision": decision, "ts": ts},
        sort_keys=True,
        separators=(",", ":"),
    )
    signature = key.sign(payload.encode()).signature.hex()
    return {"decision": decision, "signed_payload": payload, "signature": signature}


def test_signed_approval_wakes_the_parked_run(client: httpx.Client) -> None:
    incident_id, action_id = _seed_parked_red_action()
    incident = client.get(f"/api/incidents/{incident_id}").json()
    assert incident["status"] == "awaiting_approval", incident
    assert incident["actions"][0]["status"] == "awaiting_approval", incident

    key, pubkey_hex = _register_key()
    resp = client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-approval-test"})
    assert resp.status_code == 200, resp.text

    body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    resp = client.post(f"/api/approvals/{action_id}", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "action.approved"

    resolved = wait_for_resolution(client, incident_id)
    assert resolved["status"] == "resolved", resolved
    assert resolved["autonomy"] == "approved", resolved

    events = events_for(client, incident_id)
    assert any(e["type"] == "action.approved" for e in events)
    assert any(e["type"] == "action.executed" for e in events)

    chain = verify_chain(client, incident_id)
    assert chain["valid"], chain


def test_bad_signature_is_rejected(client: httpx.Client) -> None:
    incident_id, action_id = _seed_parked_red_action()
    key, pubkey_hex = _register_key()
    client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-bad-sig-test"})

    body = _sign(key, action_id=action_id, decision="approve")
    body["pubkey"] = pubkey_hex
    body["signature"] = "00" * 64  # well-formed hex, wrong signature

    resp = client.post(f"/api/approvals/{action_id}", json=body)
    assert resp.status_code == 400, resp.text

    # cleanup: the run is still parked; approve for real so it doesn't leak
    # into another test's incident list as a permanently-open incident.
    ok_body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    client.post(f"/api/approvals/{action_id}", json=ok_body)
    wait_for_resolution(client, incident_id)


def test_unknown_pubkey_is_rejected(client: httpx.Client) -> None:
    incident_id, action_id = _seed_parked_red_action()
    key, pubkey_hex = _register_key()  # deliberately never registered

    body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    resp = client.post(f"/api/approvals/{action_id}", json=body)
    assert resp.status_code == 400, resp.text

    client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-unknown-key-cleanup"})
    ok_body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    client.post(f"/api/approvals/{action_id}", json=ok_body)
    wait_for_resolution(client, incident_id)


def test_stale_timestamp_is_rejected(client: httpx.Client) -> None:
    incident_id, action_id = _seed_parked_red_action()
    key, pubkey_hex = _register_key()
    client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-stale-ts-test"})

    old_ts = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"
    body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve", ts=old_ts)}
    resp = client.post(f"/api/approvals/{action_id}", json=body)
    assert resp.status_code == 400, resp.text

    ok_body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    client.post(f"/api/approvals/{action_id}", json=ok_body)
    wait_for_resolution(client, incident_id)


def test_approval_after_resolution_is_rejected_with_409(client: httpx.Client) -> None:
    incident_id, action_id = _seed_parked_red_action()
    key, pubkey_hex = _register_key()
    client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-409-test"})

    ok_body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    resp = client.post(f"/api/approvals/{action_id}", json=ok_body)
    assert resp.status_code == 200, resp.text
    wait_for_resolution(client, incident_id)

    again = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    resp = client.post(f"/api/approvals/{action_id}", json=again)
    assert resp.status_code == 409, resp.text


def test_veto_during_the_window_escalates_instead_of_healing(client: httpx.Client) -> None:
    """A signed veto inside the real 30s window cancels the action and sends
    the incident to escalate instead of execute.

    The yellow action is seeded (scripts/seed_yellow_action.py), the same way
    the red-tier tests above seed theirs, rather than driven out of an
    error_spike injection. Live, a model has to return a confident yellow
    proposal for that injection before this test can even begin, and in the
    phase 8 run it returned a green remove_toxic at confidence 0.0 that OPA
    correctly denied, so no window opened and this test timed out on a
    working policy engine (docs/reports/FINAL_VERIFICATION.md). What is
    under test is the veto window, so the veto window is what this drives.
    The unvetoed path through a live model stays covered by
    test_scenarios.py's test_error_spike_heals.
    """
    key, pubkey_hex = _register_key()
    client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-veto-test"})

    seed = subprocess.Popen(  # noqa: S603 - fixed argv, no shell, internal test tooling
        [*COMPOSE, "exec", "-T", "core-worker", "python", "-"],  # noqa: S607
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert seed.stdin is not None and seed.stdout is not None
        seed.stdin.write(YELLOW_SEED_SCRIPT.read_text())
        seed.stdin.close()
        # Printed and flushed before the graph runs, so this lands while the
        # veto window is still open rather than after gate has timed it out.
        seeded = json.loads(seed.stdout.readline().strip())
        incident_id, action_id = seeded["incident_id"], seeded["action_id"]

        _wait_for_veto_window(client, incident_id=incident_id, action_id=action_id)

        body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="veto")}
        resp = client.post(f"/api/veto/{action_id}", json=body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["type"] == "action.rejected"

        resolved = wait_for_resolution(client, incident_id)
        assert resolved["status"] == "escalated", resolved

        events = events_for(client, incident_id)
        assert not any(e["type"] == "action.executed" for e in events), events
    finally:
        seed.wait(timeout=120)


def _wait_for_veto_window(
    client: httpx.Client, *, incident_id: str, action_id: str, timeout: float = 60.0
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in events_for(client, incident_id):
            if (
                event["type"] == "action.veto_window_opened"
                and event["payload"]["action_id"] == action_id
            ):
                return
        time.sleep(1)
    raise TimeoutError(f"no veto window opened for {action_id} within {timeout}s")


def test_verify_chain_detects_tampering(client: httpx.Client) -> None:
    incident_id, action_id = _seed_parked_red_action()
    key, pubkey_hex = _register_key()
    client.post("/api/keys", json={"pubkey": pubkey_hex, "label": "e2e-tamper-test"})
    ok_body = {"pubkey": pubkey_hex, **_sign(key, action_id=action_id, decision="approve")}
    client.post(f"/api/approvals/{action_id}", json=ok_body)
    wait_for_resolution(client, incident_id)

    valid = verify_chain(client, incident_id)
    assert valid["valid"], valid

    _corrupt_one_event(incident_id)

    tampered = verify_chain(client, incident_id)
    assert tampered["valid"] is False, tampered
    assert tampered["break_at_seq"] is not None, tampered


_CORRUPT_TEMPLATE = """
import asyncio
from aegis import db

async def main():
    async with db.connection() as conn, conn.transaction():
        await conn.execute(
            "UPDATE aegis.incident_events SET hash = 'tampered' "
            "WHERE incident_id = $1 AND seq = ("
            "  SELECT seq FROM aegis.incident_events WHERE incident_id = $1 "
            "  ORDER BY seq ASC LIMIT 1)",
            {incident_id!r},
        )
    await db.close_pool()

asyncio.run(main())
"""


def _corrupt_one_event(incident_id: str) -> None:
    script = _CORRUPT_TEMPLATE.format(incident_id=incident_id)
    subprocess.run(  # noqa: S603 - fixed argv, no shell, internal test tooling
        [*COMPOSE, "exec", "-T", "core-api", "python", "-"],  # noqa: S607
        input=script,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
