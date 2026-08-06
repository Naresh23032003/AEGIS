"""Canonical JSON and hash chaining for incident_events.

plan/02-contracts.md, Database schema: hash = sha256(prev_hash ||
canonical_json(envelope)); the first event in a chain uses
prev_hash = incident_id. plan/04-security.md, Hash-chained audit log.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: dict[str, Any]) -> bytes:
    """Sorted keys, no whitespace, UTF-8. Same helper used for hashing and
    for the signed-payload string in approvals/vetoes (plan/02)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def next_hash(prev_hash: str, envelope: dict[str, Any]) -> str:
    """sha256(prev_hash || canonical_json(envelope)), hex digest."""
    digest = hashlib.sha256()
    digest.update(prev_hash.encode("utf-8"))
    digest.update(canonical_json(envelope))
    return digest.hexdigest()
