# Architecture (Phase 0 view)

Only what exists or is committed is drawn solid. Later components are listed as planned.
See [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) for sequencing and [ADRs](adr/).

## Context

```mermaid
flowchart LR
    client["Client (open component: browser SDK vs reference CLI, ADR-0012)"]
    api["distributed-storage-api (FastAPI)"]
    db[("PostgreSQL")]
    client -->|"HTTPS (Phase 1+)"| api
    api --> db
```

## Containers (Phase 0, Docker Compose)

```mermaid
flowchart LR
    migrate["migrate (one-shot)"] -->|"alembic upgrade head"| pg[("postgres")]
    api["api"] -->|"asyncpg"| pg
    migrate -. "must complete before" .-> api
```

## Planned (not built)

```mermaid
flowchart LR
    api["distributed-storage-api<br/>identity, authz, metadata, keys, audit, storage coordinator"]
    worker["worker (first job type, ~Phase 3)<br/>repair, health prober, scrubber, GC"]
    pg[("PostgreSQL<br/>manifests, placement, jobs, leases, node health")]
    nodes["StorageNode adapters<br/>LocalBlob, SeaweedFS (optional), S3 (optional)"]
    api --> pg
    worker --> pg
    api --> nodes
    worker --> nodes
```

## Principles

- Modular monolith: one codebase, module boundaries are code boundaries (ADR-0001).
- PostgreSQL is the system of record and the job queue (ADR-0004).
- Distributed Storage owns erasure coding, placement, health, repair and integrity; storage nodes are dumb blob stores (ADR-0002).
