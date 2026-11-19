# Architecture Decision Records

Copy `0000-template.md` for a new ADR. Statuses: Proposed, Accepted, Superseded. Accepted ADRs are
changed only by a new ADR that supersedes them. The index with "must be accepted before" gates is
in [IMPLEMENTATION_PLAN.md](../../IMPLEMENTATION_PLAN.md) section 5.1.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith-and-deferred-worker.md) | Modular monolith; worker deferred | Accepted |
| [0002](0002-storagenode-interface-and-adapters.md) | StorageNode interface and adapters | Proposed |
| [0003](0003-seaweedfs-optional-adapter.md) | SeaweedFS optional adapter | Proposed |
| [0004](0004-postgresql-system-of-record-and-job-queue.md) | PostgreSQL system of record and job queue | Accepted |
| [0005](0005-erasure-coding.md) | Erasure coding scheme | Proposed |
| [0006](0006-shard-placement-and-failure-domains.md) | Placement and failure domains | Proposed |
| [0007](0007-repair-coordination.md) | Repair coordination | Proposed |
| [0008](0008-shard-integrity-and-audit.md) | Shard integrity and audit | Proposed |
| [0009](0009-upload-protocol-and-idempotency.md) | Upload protocol and idempotency | Proposed |
| [0010](0010-failure-detection.md) | Failure detection | Proposed |
| [0013](0013-tooling-and-ci.md) | Tooling and CI | Accepted |

ADR-0011 (authentication scheme) and ADR-0012 (client platform and crypto libraries) are not yet drafted.
