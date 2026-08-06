"""Loads and validates against the closed action catalog.

plan/03-agents-and-policy.md, Action catalog. Both the gate node (to look
up a proposal's real tier, not whatever the LLM guessed) and the executor
(defense in depth, independent of OPA) import this module. Nobody else
should parse catalog.yaml directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"


class CatalogError(ValueError):
    """catalog_key unknown or params fail the catalog's own param schema."""


@dataclass(frozen=True)
class CatalogAction:
    catalog_key: str
    tier: str
    effect: str
    rollback_key: str | None
    params: dict[str, Any]


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    with CATALOG_PATH.open() as f:
        loaded: dict[str, Any] = yaml.safe_load(f)
        return loaded


@lru_cache(maxsize=1)
def target_services() -> tuple[str, ...]:
    return tuple(_raw()["target_services"])


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, CatalogAction]:
    actions: dict[str, CatalogAction] = {}
    for key, spec in _raw()["actions"].items():
        actions[key] = CatalogAction(
            catalog_key=key,
            tier=spec["tier"],
            effect=spec["effect"],
            rollback_key=spec.get("rollback_key"),
            params=spec.get("params") or {},
        )
    return actions


def get_action(catalog_key: str) -> CatalogAction:
    catalog = load_catalog()
    if catalog_key not in catalog:
        raise CatalogError(f"unknown catalog_key: {catalog_key}")
    return catalog[catalog_key]


def validate_params(catalog_key: str, params: dict[str, Any]) -> None:
    """Raises CatalogError on any mismatch. Structural only: required keys
    present, types match, `in`/`enum` constraints hold. Not a general JSON
    Schema validator; the catalog's param shapes are simple enough that one
    isn't needed."""
    action = get_action(catalog_key)
    for name, spec in action.params.items():
        if name not in params:
            raise CatalogError(f"{catalog_key}: missing required param {name}")
        value = params[name]
        expected_type = spec.get("type")
        if expected_type == "string" and not isinstance(value, str):
            raise CatalogError(f"{catalog_key}.{name}: expected string")
        if expected_type == "integer" and not isinstance(value, int):
            raise CatalogError(f"{catalog_key}.{name}: expected integer")
        if "enum" in spec and value not in spec["enum"]:
            raise CatalogError(f"{catalog_key}.{name}: {value!r} not in {spec['enum']}")
        if spec.get("in") == "target_services" and value not in target_services():
            raise CatalogError(f"{catalog_key}.{name}: {value!r} not a target service")
    extra = set(params) - set(action.params)
    if extra:
        raise CatalogError(f"{catalog_key}: unexpected params {sorted(extra)}")
