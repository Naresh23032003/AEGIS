"""Ed25519 signature verification for approvals and vetoes.
plan/04-security.md, Signed approvals: "Approve, reject, and veto actions
sign the canonical JSON of {action_id, decision, ts} in the browser. The
server verifies against registered pubkeys (PyNaCl), rejects stale ts
(> 60s) and unknown keys". plan/02-contracts.md: the server checks ts is
within 60 seconds, verifies the Ed25519 signature against a registered
pubkey, then emits the event.

Encoding choice (plan/04 does not pin one): pubkey and signature are
lowercase hex strings. Not specified by the plan since the browser side
that generates and encodes these with tweetnacl does not exist until
phase 4; hex is the simplest fixed-length, copy-pasteable encoding and is
what phase 4's console must match.

The server can verify a signature but never produce one: this module has
no signing function, only verify_signature.
"""

from __future__ import annotations

from datetime import UTC, datetime

import nacl.exceptions
import nacl.signing

from aegis.chain import canonical_json

STALE_AFTER_SECONDS = 60


class InvalidSignature(ValueError):
    pass


class StaleTimestamp(ValueError):
    pass


class MalformedKey(ValueError):
    pass


def signed_payload(*, action_id: str, decision: str, ts: str) -> bytes:
    """The exact bytes a client must sign: canonical JSON of
    {action_id, decision, ts}, same canonicalization as the hash chain."""
    return canonical_json({"action_id": action_id, "decision": decision, "ts": ts})


def check_ts_fresh(ts: str, *, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StaleTimestamp(f"unparseable ts {ts!r}") from exc
    age = abs((now - parsed).total_seconds())
    if age > STALE_AFTER_SECONDS:
        raise StaleTimestamp(
            f"ts {ts!r} is {age:.0f}s old, older than the {STALE_AFTER_SECONDS}s window"
        )


def verify_signature(
    *, pubkey_hex: str, signature_hex: str, action_id: str, decision: str, ts: str
) -> None:
    """Raises InvalidSignature, StaleTimestamp, or MalformedKey; returns
    None on success. Checks freshness first so a replayed-but-validly-signed
    old payload never reaches the (slightly more expensive) crypto check."""
    check_ts_fresh(ts)
    try:
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(pubkey_hex))
    except (ValueError, nacl.exceptions.CryptoError) as exc:
        raise MalformedKey(f"bad pubkey {pubkey_hex!r}: {exc}") from exc
    message = signed_payload(action_id=action_id, decision=decision, ts=ts)
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError as exc:
        raise MalformedKey(f"bad signature encoding: {exc}") from exc
    try:
        verify_key.verify(message, signature)
    except nacl.exceptions.BadSignatureError as exc:
        raise InvalidSignature("signature does not match the payload") from exc
