# ADR-004: Rule-based detection, LLM diagnosis

## Status

Accepted.

## Context

AEGIS has two jobs that look similar but are not: noticing that something is
wrong, and figuring out why. They have different requirements. Detection
needs to be fast, cheap, and the same answer every time given the same
metrics. Diagnosis needs to read logs, metrics, and traces together and form
a hypothesis, which is exactly the kind of task an LLM is good at and a
fixed rule set is not.

## Decision

Detection is deterministic: a rules engine in
`apps/core/aegis/detection/rules.yaml` evaluates Prometheus queries and
health probes on a fixed interval. Diagnosis is an LLM node (LLM_LARGE) with
tool access to Loki, Prometheus, Tempo, and container stats.

## Consequences

An incident opens the same way every time a threshold is crossed, which
means fixtures record cleanly and MOCK_LLM=1 replays are deterministic from
the moment detection fires. The LLM only enters the loop once there is
already a confirmed anomaly, which keeps cost and latency out of the steady
state (loadgen running at baseline) and puts the token spend where it earns
something: forming a hypothesis from evidence.
