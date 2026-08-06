# ADR-001: LangGraph Postgres checkpoints instead of Temporal

## Status

Accepted.

## Context

Every incident run needs to survive a worker restart: the gate node parks a
run on a veto window or a pending approval, sometimes for minutes, and the
process holding that run can be killed and replaced. We need durable
workflow state without standing up a second orchestration system.

## Decision

Use LangGraph's `AsyncPostgresSaver` to checkpoint every node transition into
aegis-db (schema `checkpoints`). No Temporal.

## Consequences

Durability at demo scale with one database we already run. No separate
Temporal server, worker pool, or client SDK to operate or explain in a demo.
The tradeoff: LangGraph checkpointing is not a general-purpose workflow
engine. It does not give us cron schedules, child workflows, or Temporal's
operator UI. If AEGIS grows into a production system with many workflow
types, Temporal is the production path; that migration is out of scope here.
