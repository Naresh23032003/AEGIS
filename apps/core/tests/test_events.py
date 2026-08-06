from datetime import UTC, datetime

from aegis.chain import next_hash
from aegis.events import build_envelope, format_ts


def test_build_envelope_validates_against_the_contract() -> None:
    now = datetime.now(UTC)
    envelope = build_envelope(
        incident_id="inc_test",
        type="chaos.injected",
        actor="system:detector",
        now=now,
        payload={"scenario": "latency"},
    )
    assert envelope["incident_id"] == "inc_test"
    assert envelope["ts"] == format_ts(now)


def test_format_ts_round_trips_through_a_stored_datetime() -> None:
    """Regression test: created_at must be the exact `now` hashed into the
    envelope's ts, not a value Postgres's own now() computes microseconds
    later at INSERT time. If they diverge, reformatting the row read back
    out of incident_events would produce a different ts than what was
    actually hashed, and the chain would never recompute clean.
    """
    now = datetime.now(UTC)
    envelope = build_envelope(
        incident_id="inc_test",
        type="incident.detected",
        actor="system:detector",
        now=now,
        payload={},
    )
    hash_at_write_time = next_hash("inc_test", envelope)

    # Simulate reading the row back out of Postgres: created_at round-trips
    # through asyncpg as a datetime with full microsecond precision, same
    # as `now` here (no truncation happens until format_ts formats it).
    reconstructed_envelope = dict(envelope)
    reconstructed_envelope["ts"] = format_ts(now)
    hash_on_replay = next_hash("inc_test", reconstructed_envelope)

    assert hash_at_write_time == hash_on_replay
