# ADR-0006: Shard placement and failure domains

- **Status:** Proposed (D5 pending)
- **Date:** 2026-11-17
- **Related:** D5, ADR-0005, ADR-0007

## Decision (proposed)

- Each node has a `failure_domain_id`. Hard rule: at most one shard of a stripe per domain.
- Placement is chosen deterministically (rendezvous hashing over eligible domains when nodes exceed shards) and then **recorded explicitly in PostgreSQL**, which is authoritative; it is never recomputed.
- With exactly six nodes in six domains no repair target exists after one failure: the system stays degraded until a replacement joins. A seventh spare node (Compose profile) is used to demonstrate repair. The rule is never relaxed silently.
- Parity placement rotates per stripe to spread load.

## Consequences

Docker containers on one host are simulated failure domains; documentation must say so until Phase 9.
