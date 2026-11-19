# ADR-0005: Erasure coding scheme and codec abstraction

- **Status:** Proposed (D3, D4, D6 pending)
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D3, D4, D6, ADR-0006

## Decision (proposed)

- Reed-Solomon 4+2 (4 data shards, 2 parity) on six nodes: 1.5x overhead, tolerates any two losses.
- Stripe = chunk = 4 MiB of encrypted data, giving shards of about 1 MiB.
- Coding runs in the coordinator on ciphertext, which preserves zero-knowledge but means the coordinator sees full ciphertext and sizes.
- Behind an `ErasureCodec` interface; `zfec` as the production codec (licence GPLv2+ or TGPPL), optionally with a pure-Python GF(2^8) reference codec differential-tested against it.
- The manifest records `codec_id`, k, m, shard index and padding; parity bytes are not assumed portable across codecs. Note zfec's `m` is the total shard count, so 4+2 is k=4, m=6.
- Write quorum: at least k+1 = 5 verified shards before a chunk commits; missing shards queue for repair.

## Consequences

File sizes are visible to nodes (padding buckets deferred). Uploads fail when two nodes are down.
