# ADR-0003: SeaweedFS as an optional adapter and benchmark baseline

- **Status:** Proposed
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** ADR-0002, ADR-0005

## Context

SeaweedFS has its own volume-level replication and erasure coding (aimed at warm data), a master
that owns volume placement, and a filer with a separate metadata store. Layering our own erasure
coding on a SeaweedFS cluster duplicates redundancy and repair and conflicts on placement.

## Decision (proposed)

SeaweedFS is never a mandatory dependency. It may be added in Phase 9 as a per-node blob-store
adapter (replication disabled, no filer, blob-level API only) behind the `StorageNode` interface.
Its native replication/EC is a benchmark baseline for Phase 8, not part of the design.

## Consequences

Phase 0-8 need no SeaweedFS operations burden; Phase 9 must prove the adapter passes the conformance suite.
