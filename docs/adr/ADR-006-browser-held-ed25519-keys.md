# ADR-006: Browser-held Ed25519 keys for approvals

## Status

Accepted.

## Context

Yellow and red tier actions need a human decision that the server can prove
came from a specific person, not just a click the server itself could have
recorded on its own say-so. A password or session-cookie approval only
proves the request reached the server; it does not prove who authorized it,
and it gives the server the ability to forge an approval it later needs to
defend.

## Decision

Approvers hold an Ed25519 keypair generated and kept in the browser. The
console signs `{action_id, decision, ts}` client-side and posts the
signature; core-api verifies it against a registered pubkey
(`approver_keys`) and never sees the private key.

## Consequences

The server can verify an approval but cannot manufacture one, which is the
property the evidence pack and the hash chain depend on. Key management is
minimal by design (`POST /keys` registers a pubkey and a label) because this
is a demo of the trust model, not a KMS. A production deployment would add
key rotation, device binding, and recovery, none of which change the core
guarantee: the signature proves a specific key authorized this specific
action at this specific time.
