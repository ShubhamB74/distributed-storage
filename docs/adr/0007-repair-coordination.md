# ADR-0007: Repair coordination, leases and fencing

- **Status:** Proposed
- **Date:** 2026-11-17
- **Related:** ADR-0004, ADR-0006, ADR-0008

## Decision (proposed)

- `repair_jobs` has a partial unique index on `(stripe_id, shard_index)` for pending/running jobs; bulk creation uses `ON CONFLICT DO NOTHING`, so duplicates cannot exist.
- Workers claim with `SKIP LOCKED`, take a lease with heartbeat, and prioritise stripes with the fewest surviving shards. Global concurrency and bandwidth are capped.
- Repair: fetch at least k healthy shards, verify each against manifest hashes, reconstruct, verify the result equals the manifest hash, PUT under the placement's key (write-once and idempotent: same bytes is a no-op, different bytes is a conflict; amended by ADR-0014), HEAD-verify, then one transaction does `UPDATE shard_placement ... WHERE generation = g` and completes the job. Zero rows updated means discard and best-effort delete the extra blob.
- Crash-only: an expired lease returns the job to pending; no special recovery path.

## Consequences

Correctness depends on idempotent operations and the compare-and-swap, which need fault-injection tests (Phase 4).
