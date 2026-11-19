# ADR-0008: Shard integrity verification and audit

- **Status:** Proposed
- **Date:** 2026-11-17
- **Related:** ADR-0002, ADR-0007

## Decision (proposed)

1. Node contract: durable write (fsync, rename), then return computed SHA-256 and length.
2. Coordinator compares against the expected hash and performs `HEAD`.
3. Sampled read-back after upload.
4. Scrubber: random range audits against per-shard leaf hashes (for example 64 KiB leaves, stored in PostgreSQL), plus lower-frequency full reads. Works with dumb nodes and S3 range GETs.
5. **Assumption stated plainly:** a node's honouring of fsync and its retention of every byte cannot be proven remotely; sampling gives probabilistic detection, and erasure margin plus scrubbing are the mitigations.

Client-signed manifests are decided in Phase 3.
