from aegis.chain import canonical_json, next_hash


def test_canonical_json_sorts_keys_and_strips_whitespace() -> None:
    envelope = {"b": 2, "a": 1, "nested": {"z": 1, "y": 2}}
    assert canonical_json(envelope) == b'{"a":1,"b":2,"nested":{"y":2,"z":1}}'


def test_next_hash_fixed_vector() -> None:
    envelope = {"b": 2, "a": 1, "nested": {"z": 1, "y": 2}}
    digest = next_hash("inc_test123", envelope)
    assert digest == "f1eeb1cfbcd0379c48d058eec7f0c5a84828284532e88a7af87e3a83d6486ad8"
    assert len(digest) == 64


def test_next_hash_changes_with_prev_hash() -> None:
    envelope = {"type": "incident.detected"}
    first = next_hash("inc_a", envelope)
    second = next_hash("inc_b", envelope)
    assert first != second
