# Data model drafts (design only)

**No migrations exist for these.** They are inputs to the Phase 1 data-model review and will be
revised there. Entity list (draft):

- `storage_node`: id, adapter type, endpoint reference, failure_domain_id, state, last_seen, consecutive_failures
- `file`, `file_version`: ownership, version number, committed manifest reference (encrypted fields from Phase 2)
- `stripe` (one per chunk): file_version_id, index, codec_id, k, m, padding, state
- `shard_placement`: stripe_id, shard_index, node_id, content hash (SHA-256), leaf hashes, state, generation (fencing token)
- `upload_session`: id, state, expiry, idempotency data per chunk (`unique (upload_id, chunk_index)`)
- `repair_job`: stripe_id, shard_index, state, lease owner/expiry, attempt
  (partial unique index on `(stripe_id, shard_index)` while pending/running)
- `audit_event`: append-only from Phase 1 (hash chaining and signing arrive in Phase 7)

State machines: [storage-state-machines.md](storage-state-machines.md).
