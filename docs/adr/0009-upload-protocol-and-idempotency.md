# ADR-0009: Upload protocol and idempotency

- **Status:** Proposed
- **Date:** 2026-11-17
- **Related:** ADR-0004, ADR-0005

## Decision (proposed)

- Intent rows (`PLANNED` stripes and shards with expected hashes) are written **before** any blob is PUT, so orphan blobs cannot exist; deletion uses a `DELETING` tombstone state.
- Chunks are idempotent by unique `(upload_id, chunk_index)` plus ciphertext hash: same hash returns the stored result, different hash returns 409.
- Finalisation is keyed by `upload_id`; a retry returns the same `version_id`. The file version becomes visible only in one final transaction.
- Resumption: the client asks which chunk indexes and hashes are committed and resends the rest. Expired sessions become `ABORTED` and the GC deletes their shards.
