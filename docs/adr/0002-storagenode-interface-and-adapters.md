# ADR-0002: StorageNode interface and adapters

- **Status:** Accepted (D2 approved 2026-11-18); key scheme amended by ADR-0014
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D2, ADR-0003, ADR-0008

## Context

Distributed Storage owns chunking, erasure coding, placement, health tracking, repair and integrity.
Storage nodes must therefore be independent blob stores with no redundancy logic of their own.

## Decision

- `StorageNode`: `put`, `get`, `head`, `delete`, plus `health()` (approved extension, D2).
- Blob keys are the shard placement's UUID (ADR-0014); blobs are write-once. `put` returns the length and SHA-256 the node computed; the database records them and is authoritative.
- Contract for nodes: write to a temp file, fsync, rename, fsync the directory before acknowledging.
- Adapters: `LocalBlobStorage` first (Phase 1), SeaweedFS and S3-compatible later and optional.
- One shared conformance test suite that every adapter must pass.

## Alternatives considered

Adding `list` (not needed if rows are never deleted before blobs; may become an optional capability); using a cluster product's native redundancy (ADR-0003).

## Consequences

Adapter drift is controlled by the conformance suite; nodes stay trivially replaceable.

## Revisit when

An adapter cannot satisfy the contract (for example, no durable-write guarantee).
