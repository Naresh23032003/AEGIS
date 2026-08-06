"""plan/04-security.md, Signed approvals. aegis.security verifies but never
signs; these tests sign with a real PyNaCl keypair, the same way phase 3's
integration test signs an approval, and check the server-side checks: valid
signature, wrong key, tampered payload, and a stale ts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import nacl.signing
import pytest
from aegis import security


def _sign(signing_key: nacl.signing.SigningKey, *, action_id: str, decision: str, ts: str) -> str:
    message = security.signed_payload(action_id=action_id, decision=decision, ts=ts)
    return bytes(signing_key.sign(message).signature).hex()


def test_valid_signature_verifies() -> None:
    key = nacl.signing.SigningKey.generate()
    pubkey_hex = bytes(key.verify_key).hex()
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    signature_hex = _sign(key, action_id="act_1", decision="approve", ts=ts)

    security.verify_signature(
        pubkey_hex=pubkey_hex,
        signature_hex=signature_hex,
        action_id="act_1",
        decision="approve",
        ts=ts,
    )


def test_signature_from_wrong_key_is_rejected() -> None:
    signer = nacl.signing.SigningKey.generate()
    other = nacl.signing.SigningKey.generate()
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    signature_hex = _sign(signer, action_id="act_1", decision="approve", ts=ts)

    with pytest.raises(security.InvalidSignature):
        security.verify_signature(
            pubkey_hex=bytes(other.verify_key).hex(),
            signature_hex=signature_hex,
            action_id="act_1",
            decision="approve",
            ts=ts,
        )


def test_signature_over_a_different_action_id_is_rejected() -> None:
    key = nacl.signing.SigningKey.generate()
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    signature_hex = _sign(key, action_id="act_1", decision="approve", ts=ts)

    with pytest.raises(security.InvalidSignature):
        security.verify_signature(
            pubkey_hex=bytes(key.verify_key).hex(),
            signature_hex=signature_hex,
            action_id="act_2",  # tampered after signing
            decision="approve",
            ts=ts,
        )


def test_stale_timestamp_is_rejected() -> None:
    key = nacl.signing.SigningKey.generate()
    ts = (datetime.now(UTC) - timedelta(seconds=120)).isoformat().replace("+00:00", "Z")
    signature_hex = _sign(key, action_id="act_1", decision="approve", ts=ts)

    with pytest.raises(security.StaleTimestamp):
        security.verify_signature(
            pubkey_hex=bytes(key.verify_key).hex(),
            signature_hex=signature_hex,
            action_id="act_1",
            decision="approve",
            ts=ts,
        )


def test_malformed_pubkey_is_rejected() -> None:
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with pytest.raises(security.MalformedKey):
        security.verify_signature(
            pubkey_hex="not-hex",
            signature_hex="00" * 64,
            action_id="act_1",
            decision="approve",
            ts=ts,
        )
