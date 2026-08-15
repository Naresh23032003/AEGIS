# ADR-003: Redis Streams instead of Kafka or NATS

## Status

Accepted.

## Context

Every event (chaos, detection, agent steps, actions, verification) needs to
reach console WebSocket clients in near real time, and the volume is one
incident's worth of events at a time, not a production fleet's.

## Decision

Publish to a single Redis Stream, `aegis:events`, on its own container
(`aegis-redis`). core-api tails it with `XREAD` and fans out to WebSocket
clients. No Kafka, no NATS.

## Consequences

One redis:7 container to run instead of a multi-broker cluster or a second
message system. It is a second Redis, not the shop cache's: phase 9 split
the two after a live run showed `restart_dependency` restarting the event
bus mid-incident (docs/reports/FINAL_VERIFICATION.md). The image is already
in the stack either way, so the cost of the split is one more container. Consumer
groups are available if we later need multiple independent readers, but nothing in this
scope needs them: core-api's single tailing process is enough. The tradeoff
is throughput and retention: Redis Streams is not built for the sustained
high-volume, long-retention workloads Kafka handles. At AEGIS's scale, one
incident at a time, event history also persisted in Postgres, that ceiling
is not a constraint.
