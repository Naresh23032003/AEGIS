# ADR-007: Recorded LLM fixtures (MOCK_LLM=1)

## Status

Accepted.

## Context

The headline demo needs to run for a hiring reviewer who has no Groq API
key, possibly no internet connection, and no patience for a live model's
variance in timing or wording. It also needs to run the same way in CI on
every push.

## Decision

Every LLM call goes through `aegis.llm`. With `MOCK_LLM=1`, that module
replays a recorded fixture instead of calling Groq. Fixtures are recorded
from real runs (`make record-fixtures SCENARIO=x`) once a scenario heals
live, and replay deterministically after that.

## Consequences

`docker compose up` plus one click heals a real, injected fault end to end
with no API key, which is the non-negotiable quality bar in PLAN.md. CI runs
the same fixtures instead of burning API budget or flaking on model
variance. The cost is upkeep: a fixture goes stale if the prompt, the
contract schema, or the target system's behavior changes, and stale
fixtures fail loudly (schema validation) rather than silently.
