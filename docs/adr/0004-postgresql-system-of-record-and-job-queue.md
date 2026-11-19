# ADR-0004: PostgreSQL as system of record and job queue

- **Status:** Accepted (D1 approved 2026-11-17)
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D1, ADR-0001, ADR-0007, ADR-0009

## Context

Upload sessions, manifests, shard placement, node health and repair jobs are tightly coupled
state. A separate broker would require dual writes (commit to the database, then enqueue) and
its own delivery semantics, while idempotency and deduplication would still have to live in the
database.

## Decision

- PostgreSQL is the authoritative store for metadata, manifests, shard placement, node health,
  leases and the job queue.
- Jobs are claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, with lease expiry and a fencing
  token (a generation counter) for long-running ownership.
- **Redis, RabbitMQ and Celery are deferred** and added only if future measurements show the
  PostgreSQL queue is a bottleneck (Phase 8).
- Delivery is at-least-once. Every job must be idempotent.
- No database transaction is held open across network I/O.

## Alternatives considered

- RabbitMQ + Celery: more components and a dual-write problem for no demonstrated need.
- Redis queues: a second state store whose consistency we would have to reason about.
- Distributed locks (Redis, ZooKeeper): a second consistency authority; leases in PostgreSQL suffice.

## Consequences

- Enqueue is atomic with the state change that caused it.
- Polling adds latency, and throughput has a ceiling (acceptable at this project's scale).
- Idempotency, leases and compare-and-swap on `generation` must be implemented and tested carefully (Phases 3 and 4).

## Revisit when

Load tests show job-claim latency or lock contention violating an agreed target, with metrics
that attribute the problem to the queue.
