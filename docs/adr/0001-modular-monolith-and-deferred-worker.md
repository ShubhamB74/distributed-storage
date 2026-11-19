# ADR-0001: Modular monolith; worker process deferred

- **Status:** Accepted (D10 approved 2026-11-17)
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D10, ADR-0004

## Context

Distributed Storage has many logical components (identity, authorization, metadata, keys, storage
coordination, audit, integrity, recovery, detection). Splitting them into services early adds
network failure modes, deployment overhead and distributed-transaction problems before any of
them has proven it needs independent scaling or isolation.

## Decision

1. One Python package (`distributed_storage`) with module boundaries as code boundaries. Modules are added
   when their phase starts (Phase 0 has only `api`, `core`, `db`).
2. One deployable API process in Phase 0.
3. **No worker process in Phase 0.** A worker is a second entrypoint of the same package, created
   when the first real background job type exists (expected Phase 3: upload-session expiry/GC;
   Phase 4 adds repair, health probing and scrubbing). Phase 0's `migrate` container is a one-shot
   job, not a worker.
4. Storage nodes are separate processes by nature (Phase 4), reached through the `StorageNode`
   interface (ADR-0002).

## Alternatives considered

- Microservices per logical component: unjustified operational cost and consistency problems.
- Worker container from Phase 0: an idle process with nothing to do, and a contract guessed too early.

## Consequences

- Simple local development, debugging and testing; one transaction boundary in PostgreSQL.
- Module boundaries need discipline (no cross-module reaching into internals) because the compiler will not enforce them.
- Introducing the worker later requires adding a Compose service and entrypoint, which is small.

## Revisit when

A module needs independent scaling, a different security boundary, or a different release cadence,
supported by measurements or a threat-model requirement.
