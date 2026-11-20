# Glossary

- **DEK / KEK:** data encryption key / key encryption key (Phase 2).
- **Chunk:** a fixed-size piece of an encrypted file (planned: 4 MiB).
- **Stripe:** the set of shards produced by erasure-coding one chunk.
- **Shard:** one erasure-coded fragment, stored on one storage node; immutable (write-once), keyed by its placement ID, with its SHA-256 recorded in PostgreSQL.
- **k+m coding:** k data shards plus m parity shards; any k suffice to reconstruct. Planned: 4+2.
- **Failure domain:** a set of components that can fail together (node, host, rack, zone).
- **Lease / fencing token:** time-limited ownership of a job / a counter that rejects stale owners.
- **Liveness / readiness:** the process is up / the service can do useful work.
