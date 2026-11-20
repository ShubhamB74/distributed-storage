# ADR-0014: Shard blob addressing (placement-addressed, write-once)

- **Status:** Accepted (D14 approved 2026-11-18)
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D14, ADR-0002, ADR-0007, ADR-0008. Amends ADR-0002 (key scheme) and the
  "idempotent, content-addressed PUT" wording in ADR-0007; both have been updated.

## Context

ADR-0002 proposed content-addressed blobs (key = SHA-256 of shard bytes). Implementing deletion for
Phase 1 exposed a hazard: with content addressing, two placements on one node can reference the same
blob, so deleting needs reference counting. A race between "delete the last reference" and "a new
upload that reuses the same content" can delete a blob a committed placement still points to, which
is silent data loss. The benefit that justifies this complexity (deduplication) disappears once data
is encrypted with random nonces (Phase 2), and cross-user dedupe would leak file equality.

## Decision

- Blob key = the shard placement's UUID. Blobs are **write-once**: a PUT to an existing key with
  identical bytes is a no-op success; with different bytes it fails with a conflict.
- The SHA-256 and length of every shard are recorded in PostgreSQL (authoritative) and verified on
  upload, on download, on repair and by scrubbing. The node returns the hash it computed on PUT.
- Repair writes the reconstructed shard under the same key to a different node, so repair stays
  idempotent: same key and same bytes is a no-op, different bytes is a detected error.
- Deleting a blob is tied to exactly one placement row (the `DELETING` tombstone protocol), so no
  reference counting exists.

## Alternatives considered

- Content-addressed keys with reference counting: needs a race-free refcount and a GC protocol, for
  a benefit (dedupe) that encryption removes.
- Content-addressed keys without dedupe (key includes the placement ID): equivalent to this decision
  with a longer key.

## Consequences

- Blob names are not self-verifying; integrity depends on the database hash, which is authoritative
  anyway. Losing PostgreSQL loses the ability to find or verify blobs (backups are a Phase 6/9 topic).
- Simpler deletion and no shared-blob state.

## Revisit when

A future feature genuinely needs cross-file deduplication, for example for public, unencrypted data.
