# ADR-005: Closed action catalog

## Status

Accepted.

## Context

The remediation agent decides what to do about an incident, but "decides
what to do" cannot mean "writes a shell command." Free-form execution is the
single biggest risk surface in an LLM-driven ops system, and it is also the
one most vulnerable to prompt injection through logs or metric labels an
attacker controls.

## Decision

The remediation agent chooses only from a closed, pre-audited action
catalog (plan/03-agents-and-policy.md, Action catalog). Each catalog entry
maps to one hardened executor function. There is no code path from an
`ActionProposal` to a shell. `shell=True` is banned repo-wide.

## Consequences

Every action AEGIS can take is knowable in advance, testable in advance, and
listed in the console's policy table (`GET /catalog`). A compromised or
confused model can propose a bad choice among the catalog's options, but it
cannot invent a new one. The cost is flexibility: a fault that needs an
action outside the catalog cannot be healed autonomously, only escalated.
That is the intended failure mode, not a gap to close later.
