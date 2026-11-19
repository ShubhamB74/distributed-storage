# Distributed Storage — Master Implementation Plan

**Document status:** v0.2 — Phase 0 in progress
**Last updated:** 2026-11-17
**Role of this file:** the single source of truth for scope, sequencing and progress. If code, chat history and this file disagree, this file wins until it is deliberately updated (see §2.4).

> **Phase 0 implementation started on 2026-11-17** after owner approval of D1 and D7–D10. Phases 1–9 are Planned and must not start without a phase-gate review. Nothing is *Implemented*, *Tested* or *Completed* yet: the Phase 0 files have been delivered but not yet merged or run in CI (see the §6.2 evidence column).

---

## 1. Purpose and how to use this document

Distributed Storage is a self-hostable, zero-knowledge, fault-tolerant distributed file storage system, built to gain real experience in distributed systems and security engineering.

This plan:

1. Defines the ten phases (0–9) with objectives, features, dependencies, deliverables and acceptance criteria.
2. Tracks status with strict, evidence-based definitions (§2).
3. Keeps **future phases at planning level** until they begin. Detailed task breakdowns exist only for Phase 0 (tasks 0.1–0.9, which are *subtasks of Phase 0*, not independent phases).
4. Records architectural decisions, open decisions and lock-in guardrails so early phases do not constrain later ones (§6–§8).

---

## 2. Status model and update protocol

### 2.1 Status definitions

| Status | Meaning | Required evidence |
|---|---|---|
| **Planned** | Scoped but not started. | Entry in this file. |
| **In progress** | Work has started; not yet merged or not yet meeting the next level. | Branch/PR reference. |
| **Implemented** | Code/config is merged. Says nothing about correctness. | Merged PR/commit reference. |
| **Tested** | Automated tests required by the task pass in CI, including the tests named in its acceptance criteria. | CI run reference + test names. |
| **Completed** | Every acceptance criterion is met **and** docs/ADRs are updated **and** the owner has signed off at the phase gate. | Gate checklist (§2.3) filled in and approved. |

Rules:

- Status only moves forward through the levels above, one at a time. A task cannot be *Tested* without being *Implemented*.
- **Code written ≠ completed.** A phase is *Completed* only when all its tasks are *Tested* and the phase gate is approved.
- A regression found later moves the affected item back to *In progress* and is noted in the change log.
- Security properties are tracked separately in `docs/security-claims.md`: a claim is listed only with its assumptions and the test/experiment that supports it. No evidence, no claim.

### 2.2 Phase-level board

| Phase | Name | Status | Gate approved |
|---|---|---|---|
| 0 | Engineering Foundation | In progress | No |
| 1 | Identity, Metadata and Storage Foundation | Planned | No |
| 2 | Cryptography and Key Management | Planned | No |
| 3 | Chunked and Resumable File Operations | Planned | No |
| 4 | Distributed Storage Engine | Planned | No |
| 5 | Secure Sharing and Access Control | Planned | No |
| 6 | Recovery and Data Protection | Planned | No |
| 7 | Security Intelligence | Planned | No |
| 8 | Scalability and Observability | Planned | No |
| 9 | Cloud Deployment and Production Hardening | Planned | No |

### 2.3 Phase gate checklist (applied at the end of every phase)

- [ ] All task acceptance criteria met, with test/CI evidence recorded.
- [ ] Documentation updated (architecture, runbook, configuration).
- [ ] ADRs for decisions made in the phase are Accepted; superseded ones marked.
- [ ] `docs/security-claims.md` updated: every claim has assumptions and evidence, and unsupported claims are removed.
- [ ] Known limitations and partially tested areas listed explicitly (not hidden).
- [ ] Review of the *next* phase's scope against what was learned (no future phase starts without this review).
- [ ] Owner sign-off recorded in the change log.

### 2.4 Change protocol

- Scope, sequencing or architectural changes require an entry in the change log (§10) and, where architectural, an ADR. No silent changes.
- Update this file in the same PR as the work it describes.

---

## 3. Roadmap overview

| Phase | Depends on | Deliverable |
|---|---|---|
| 0 Engineering Foundation | none | Reproducible development environment with tested infrastructure |
| 1 Identity, Metadata and Storage Foundation | 0 | Working storage foundation with interchangeable storage backends |
| 2 Cryptography and Key Management | 1 | Server stores encrypted data without possessing plaintext file keys |
| 3 Chunked and Resumable File Operations | 1, 2 | Reliable encrypted file upload and download |
| 4 Distributed Storage Engine | 1, 3 | Recover encrypted files despite storage-node failures |
| 5 Secure Sharing and Access Control | 2, 3 | Secure file sharing with controlled access |
| 6 Recovery and Data Protection | 2, 3, 4 | Recoverability of both encryption access and stored data |
| 7 Security Intelligence | 1, 3 (audit hooks from 1) | Security monitoring and attack-response capabilities |
| 8 Scalability and Observability | 4 (and 5–7 as available) | Measured scalability, reliability and performance |
| 9 Cloud Deployment and Production Hardening | all | Deployable and demonstrable distributed storage platform |

---

## 4. Cross-cutting principles

1. **Never invent cryptography.** Use established, reviewed algorithms, protocols and libraries (selection recorded in an ADR in Phase 2).
2. **No hardcoded secrets.** Configuration is environment-driven; secrets fail closed.
3. **Claims policy.** "Zero-knowledge", "tamper-evident", "fault-tolerant" and similar claims appear in docs only after their supporting tests pass, and always with assumptions (see §2.1).
4. **Reproducible experiments over unsupported claims.** Performance, durability and detection claims come with a documented method and script.
5. **Smallest sufficient technology.** A component is added when a requirement or measurement justifies it, and is recorded in an ADR.
6. **Modular monolith first.** Module boundaries are code boundaries, not deployment boundaries, unless an ADR says otherwise.
7. **Honest simulation.** Containers on one host simulate failure domains; docs must say so until Phase 9 provides real separation.
8. **Tests ship with implementations.** Fault-injection and property-based tests are first-class for storage and coordination logic.

---

## 5. Baseline architecture (proposed, pending formal approval)

- **One codebase; API process first.** The background worker (same package, separate entrypoint) is deferred until the first real job type exists (D10, approved; ADR-0001).
- **PostgreSQL** is the authoritative store for metadata, manifests, shard placement, node health, leases and the job queue (`FOR UPDATE SKIP LOCKED`). Redis/RabbitMQ/Celery are not part of the baseline (D1, approved; ADR-0004); Phase 8 may add them only if measurements justify it.
- **StorageNode interface:** `put`, `get`, `head`, `delete`, plus `health()` (extension awaiting approval, D2). Nodes are independent blob stores with no replication or erasure coding of their own. Adapters: `LocalBlobStorage` first; SeaweedFS and S3-compatible adapters later and optional.
- **Distributed Storage owns:** chunking, erasure coding, shard placement and failure-domain awareness, node health tracking, reconstruction and repair, shard integrity verification.
- **Shards are immutable and content-addressed** (key = SHA-256 of shard bytes).
- **Coordination:** transactions + unique constraints for dedupe, leases with fencing tokens for long-running ownership, no distributed lock service.
- **Erasure coding (Phase 4):** 4+2 on six nodes, optional seventh spare for repair demonstrations; write quorum k+1 = 5 verified shards (D3); details finalized in ADR-0005.

### 5.1 ADR index

| ADR | Title | Status | Must be Accepted before |
|---|---|---|---|
| 0001 | Modular monolith plus worker (worker deferred) | **Accepted** (D10) | Phase 0 completes |
| 0002 | StorageNode interface and adapters | Proposed (drafted in `docs/adr/`) | Phase 1 starts |
| 0003 | SeaweedFS as optional adapter and benchmark baseline | Proposed (drafted in `docs/adr/`) | Phase 9 starts |
| 0004 | PostgreSQL as system of record and job queue | **Accepted** (D1) | Phase 0 completes |
| 0005 | Erasure coding: codec interface, 4+2, stripe size | Proposed (drafted in `docs/adr/`) | Phase 4 starts |
| 0006 | Shard placement and failure domains | Proposed (drafted in `docs/adr/`) | Phase 4 starts |
| 0007 | Repair coordination: leases and fencing | Proposed (drafted in `docs/adr/`) | Phase 4 starts |
| 0008 | Shard integrity and audit sampling | Proposed (drafted in `docs/adr/`) | Phase 4 starts |
| 0009 | Upload protocol and idempotency | Proposed (drafted in `docs/adr/`) | Phase 3 starts |
| 0010 | Failure detection and repair grace periods | Proposed (drafted in `docs/adr/`) | Phase 4 starts |
| 0011 | Authentication scheme | Not drafted | Phase 1 starts |
| 0012 | Client platform and crypto library selection | Not drafted | Phase 2 starts |
| 0013 | Tooling: Python version, package manager, DB driver, CI provider, integration-test database | **Accepted** (D7, D8, D9) | Phase 0 implementation starts |

Further ADRs (key hierarchy, nonce strategy, metadata encryption scope, sharing and revocation semantics, recovery scheme, audit log design) are added when their phases are planned in detail.

---

## 6. Phase 0 — Engineering Foundation (detailed)

**Status:** In progress (started 2026-11-17).
**Objective:** establish a reproducible, tested engineering baseline without implementing any storage, identity or crypto functionality.
**Dependencies:** none.
**Deliverable:** reproducible development environment with tested infrastructure.

### 6.1 Technology commitments and deferrals

Phase 0 commits to the minimum needed to run and test an API with a database. It must not pre-commit later technology.

| Committed in Phase 0 (D7, D8, D9 approved) | Explicitly deferred |
|---|---|
| Python 3.12, FastAPI, PostgreSQL | Redis, RabbitMQ, Celery (Phase 8, only if measured) |
| SQLAlchemy 2.x (async) + asyncpg + Alembic; `uv` | SeaweedFS and S3 adapters (Phase 9) |
| Docker Compose (postgres, api) | Storage-node containers (Phase 4) |
| pytest, ruff, mypy (implementer defaults, see D13) | Next.js frontend / client SDK (Phase 2, ADR-0012) |
| GitHub Actions CI (D8) | Nginx/TLS termination (Phase 9) |
| Structured JSON logging | Prometheus, Grafana, Locust (Phase 8) |
| | Cryptographic libraries (Phase 2) |
| | Worker service (deferred until the first job type exists; D10 approved) |

### 6.2 Task board

| ID | Task | Status | Evidence |
|---|---|---|---|
| 0.1 | Repository and tooling | In progress | Delivered: `pyproject.toml`, layout, Makefile, pre-commit. Not yet run: `uv.lock` must be generated and committed by the owner. |
| 0.2 | Configuration and secrets | In progress | Delivered with unit tests (written, not yet run: pydantic was unavailable in the authoring sandbox). |
| 0.3 | Docker Compose | In progress | Delivered: Dockerfile, Compose (postgres, one-shot migrate, api). YAML parses; not built or started. |
| 0.4 | Database migrations | In progress | Delivered: async Alembic env, empty baseline `0001`, naming convention. Compiles; migration cycle not yet run. |
| 0.5 | Structured logging | In progress | Delivered. Redaction/formatter logic exercised ad hoc with the stdlib in the sandbox (all checks passed); pytest suite not yet run. |
| 0.6 | Health checks | In progress | Delivered: `/healthz`, `/readyz`, app factory. Compiles; integration and Compose smoke tests not yet run. |
| 0.7 | Test harness | In progress | Delivered: markers, per-test throwaway databases, isolation meta-tests. Compiles; not yet run against PostgreSQL. |
| 0.8 | CI pipeline | In progress | Delivered: workflow with quality, integration, docker, compose-smoke, security, docs jobs. YAML parses; never executed on GitHub. |
| 0.9 | Architecture documentation and ADRs | In progress | Delivered: architecture, ADRs 0001-0010 and 0013, threat-model stub, claims register, data-model drafts. Link check not yet run. |

All tasks are **In progress**, not Implemented: *Implemented* requires a merged commit and *Tested* requires green CI, neither of which exists yet.

Suggested order: 0.1 → 0.2 → 0.3 → 0.4 → (0.5, 0.6, 0.7 in any order) → 0.8; 0.9 runs in parallel and is finalized last.

### 0.1 Repository and tooling

- **Objective:** conventional, reproducible project layout and quality tooling.
- **Files:** `pyproject.toml`, `uv.lock` (uv, D7), `src/distributed_storage/` (package with `api/`, `core/`, `db/` only), `tests/{unit,integration,fault}/`, `.editorconfig`, `.gitignore`, `.pre-commit-config.yaml`, `README.md`, `CONTRIBUTING.md`, `Makefile` (or `justfile`).
- **Implementation details:** `src` layout; ruff (lint + format), mypy, pytest configured; single-command setup and check targets. Do not create empty packages for future phases.
- **Dependencies:** none.
- **Acceptance criteria:** fresh clone → documented setup command → check command passes.
- **Testing requirements:** smoke test imports the package; same commands run in CI (0.8).

### 0.2 Configuration and secrets

- **Objective:** typed, environment-driven configuration that fails closed.
- **Files:** `src/distributed_storage/core/config.py`, `.env.example`, `scripts/gen-dev-env` (generates throwaway local secrets), `docs/configuration.md`, `tests/unit/test_config.py`.
- **Implementation details:** pydantic-settings; secret fields use secret types and have no defaults; support `*_FILE` variables for mounted secrets; dev/test/prod profiles; settings objects never print secret values.
- **Dependencies:** 0.1.
- **Acceptance criteria:** application refuses to start when a required secret is missing; `.env.example` contains no real secrets; settings repr masks secrets.
- **Testing requirements:** unit tests for validation, missing-secret failure, masking, `*_FILE` loading.

### 0.3 Docker Compose

- **Objective:** one-command local environment.
- **Files:** `Dockerfile` (multi-stage, non-root), `docker-compose.yml`, `.dockerignore`, `docs/dev-environment.md`.
- **Implementation details:** services `postgres` (pinned major version, named volume, healthcheck) and `api` (depends on healthy postgres). Credentials come from environment/secret files, never from the Compose file. No storage-node or worker containers yet (D10 approved); a one-shot `migrate` job runs before the API.
- **Dependencies:** 0.1, 0.2.
- **Acceptance criteria:** `docker compose up` yields healthy services; containers run as non-root; `down -v` leaves no residue; no credentials appear in tracked files.
- **Testing requirements:** CI job brings up Compose and checks readiness (after 0.6).

### 0.4 Database migrations

- **Objective:** versioned, reversible schema management.
- **Files:** `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_baseline.py`, `src/distributed_storage/db/{engine,session}.py`, `docs/database.md`.
- **Implementation details:** SQLAlchemy 2.x async API with `asyncpg` (D7), async Alembic `env.py`; constraint/index naming convention set up now (hard to retrofit); baseline migration contains infrastructure only. **No domain tables until the Phase 1 data model is approved.**
- **Dependencies:** 0.2, 0.3.
- **Acceptance criteria:** `upgrade head` → `downgrade base` → `upgrade head` succeeds on an empty database; autogenerate reports no drift.
- **Testing requirements:** integration test runs the migration cycle on real PostgreSQL; drift test.

### 0.5 Structured logging

- **Objective:** consistent, safe, machine-readable logs.
- **Files:** `src/distributed_storage/core/logging.py`, `src/distributed_storage/api/middleware.py` (request/correlation ID), `docs/logging.md`, `tests/unit/test_logging.py`.
- **Implementation details:** JSON output with timestamp, level, service, request and correlation IDs; redaction of sensitive keys (authorization, password, token, key-like and ciphertext-like fields); no request-body logging; event-naming convention documented.
- **Dependencies:** 0.1, 0.2.
- **Acceptance criteria:** logs are valid JSON; request ID is propagated and returned in a response header; sensitive fields are masked.
- **Testing requirements:** unit tests for formatting and redaction, including nested structures.

### 0.6 Health checks

- **Objective:** distinguish liveness from readiness.
- **Files:** `src/distributed_storage/api/main.py` (app factory), `src/distributed_storage/api/health.py`, `tests/integration/test_health.py`.
- **Implementation details:** `/healthz` has no dependencies; `/readyz` checks database connectivity and that migrations are at head; responses expose no internals.
- **Dependencies:** 0.3, 0.4.
- **Acceptance criteria:** `/readyz` returns 503 when PostgreSQL is unavailable and 200 when ready; `/healthz` stays 200 while the process is alive.
- **Testing requirements:** integration tests, including stopping the database.

### 0.7 Test harness

- **Objective:** a test structure that supports unit, integration and later fault-injection and property tests.
- **Files:** `tests/conftest.py`, `tests/integration/conftest.py`, pytest configuration (markers `unit`, `integration`, `fault`, `slow`; strict markers), coverage configuration, `tests/README.md`.
- **Implementation details:** PostgreSQL via Docker Compose locally and a service container in CI, real PostgreSQL only (D9); isolation between tests; deterministic seeds; conventions for fault-injection tests documented.
- **Dependencies:** 0.1, 0.3, 0.4.
- **Acceptance criteria:** unit tests run without Docker; integration tests run against real PostgreSQL; unknown markers fail.
- **Testing requirements:** meta-tests confirming fixture isolation.

### 0.8 CI pipeline

- **Objective:** automated verification of every change.
- **Files:** GitHub Actions workflow (D8), secret-scan configuration, dependency-update configuration.
- **Implementation details:** jobs for lint/format, type check, unit tests, integration tests with a PostgreSQL service, migration cycle, container build, secret scan, dependency audit; least-privilege permissions; pinned third-party actions.
- **Dependencies:** 0.1–0.7.
- **Acceptance criteria:** green on clean main; a deliberate lint error, committed fake secret, and broken migration each fail CI (verified once on throwaway branches).
- **Testing requirements:** recorded CI evidence for the negative checks.

### 0.9 Architecture documentation and ADRs

- **Objective:** capture design intent so decisions can be defended and revisited.
- **Files:** `docs/architecture.md` (Mermaid diagrams: context and containers), `docs/adr/0000-template.md`, ADR files per §5.1, `docs/threat-model.md` (scope and assumptions stub), `docs/security-claims.md` (initially: "no claims yet"), `docs/data-model/` (design-only drafts of state machines and entities, no migrations), `docs/glossary.md`.
- **Implementation details:** ADR template with context, decision, alternatives, consequences, status. ADRs 0001, 0004 and 0013 are Accepted during Phase 0; later ADRs remain Proposed until their phase.
- **Dependencies:** informed by all tasks; finalized last.
- **Acceptance criteria:** ADRs follow the template; diagrams render; links verified; documentation matches the implemented Phase 0.
- **Testing requirements:** link/markdown check in CI.

### 6.3 Phase 0 acceptance criteria (phase level)

- [ ] Fresh clone to green checks follows documented steps only.
- [ ] `docker compose up` yields healthy `postgres` and `api`.
- [ ] Migration cycle verified in CI on real PostgreSQL.
- [ ] CI blocks lint, type, test, secret and migration failures.
- [ ] No secrets in repository history; secret scan passes.
- [ ] ADRs 0001, 0004, 0013 Accepted; other ADRs drafted as Proposed.
- [ ] Phase gate (§2.3) approved.

---

## 7. Phases 1–9 (planning level)

> These sections are intentionally high-level. Task breakdowns, file lists and detailed designs are written only when the previous phase passes its gate and the owner approves the phase start. All features below are **Planned**.

### Phase 1 — Identity, Metadata and Storage Foundation

- **Objective:** accounts, metadata and the storage abstraction working end to end against a local backend.
- **Features:** authentication and authorization; device registration; PostgreSQL metadata models; `StorageNode` interface; `LocalBlobStorage`; node registration and health tracking; basic file upload/download.
- **Dependencies:** Phase 0 Completed; ADR-0002 and ADR-0011 Accepted; Phase 1 data model approved.
- **Deliverable:** working storage foundation with interchangeable storage backends.
- **Acceptance criteria (planning level):**
  - A registered user can upload and download a file through `LocalBlobStorage`; users cannot access each other's files (authorization tests independent of authentication).
  - A reusable `StorageNode` conformance test suite exists and `LocalBlobStorage` passes it; future adapters must pass the same suite.
  - Node health state transitions are unit-tested.
  - **The unencrypted upload path is development-only**, gated by configuration, labelled as such, and must be removed or disabled by Phase 2's gate. No zero-knowledge claim is made in Phase 1.
- **Design notes (guardrails, see §8):** manifest/shard schema is designed to accommodate chunks, stripes, codec identifiers and shard indexes from the start (Phase 1 may write a single-shard "no coding" layout); device records accommodate public keys that are populated in Phase 2; an append-only audit-event table starts here so Phase 7 does not retrofit it.

### Phase 2 — Cryptography and Key Management

- **Objective:** the server stores encrypted data and encrypted metadata without possessing plaintext file keys.
- **Features:** client-side encryption/decryption; key generation and derivation; DEK/KEK hierarchy; key wrapping; encrypted metadata; nonce management; key rotation and device key management.
- **Dependencies:** Phase 1 Completed; ADR-0012 (client platform and library selection) and key-hierarchy/nonce ADRs Accepted.
- **Deliverable:** server stores encrypted data without possessing plaintext file keys.
- **Acceptance criteria (planning level):**
  - Automated inspection of database and storage contents finds no plaintext file content, file names or plaintext keys.
  - Known-answer tests for cryptographic operations; nonce-uniqueness tests; tamper tests (modified ciphertext, wrapped key or metadata is rejected).
  - Key rotation and device-key workflows tested end to end, with rotation semantics documented (re-wrap versus re-encrypt).
  - Phase 1's plaintext path is removed or disabled.
  - Threat model and assumptions behind the zero-knowledge claim documented in `docs/security-claims.md`.
- **Open questions:** client platform (browser Web Crypto versus a reference CLI first; browser support for password hashing and curve operations must be verified before committing); separation of the authentication secret from key-derivation material.

### Phase 3 — Chunked and Resumable File Operations

- **Objective:** reliable encrypted upload and download of large files.
- **Features:** chunked uploads; upload sessions; idempotency; interrupted-upload recovery; encrypted manifests; file versioning; integrity verification.
- **Dependencies:** Phases 1 and 2 Completed; ADR-0009 Accepted.
- **Deliverable:** reliable encrypted file upload and download.
- **Acceptance criteria (planning level):**
  - Killing the API mid-upload and resuming yields a byte-identical file.
  - Replaying a chunk is safe; a conflicting replay is rejected.
  - Corrupted or reordered chunks and manifests are detected.
  - Older versions can be listed and downloaded.
  - Expired upload sessions are cleaned up without orphaned blobs.
- **Design notes:** the first background job type (session expiry/GC) may introduce the worker process and the PostgreSQL queue here; client-signed manifests are a decision to take in this phase.

### Phase 4 — Distributed Storage Engine

- **Objective:** recover encrypted files despite storage-node failures, with Distributed Storage owning redundancy.
- **Features:** Reed-Solomon 4+2; six storage nodes and an optional seventh spare; shard placement; failure-domain awareness; node failure detection; reconstruction; automatic repair; crash-safe coordinator operations.
- **Dependencies:** Phases 1 and 3 Completed; ADRs 0005–0008 and 0010 Accepted.
- **Deliverable:** recover encrypted files despite storage-node failures.
- **Acceptance criteria (planning level):**
  - With six nodes, any two nodes can be lost and downloads remain byte-identical.
  - Single-node loss with a spare triggers repair exactly once per shard, including under concurrent workers.
  - Fault injection at each coordinator state transition recovers to a consistent state.
  - Writes require the agreed quorum; placement never puts two shards of a stripe in one failure domain (invariant tested).
  - Deliberately corrupted shards are detected by scrubbing; reconstructed shards match manifest hashes.
  - Documentation states that failure domains are simulated in Compose.
- **Notes:** the behaviour with exactly six nodes and no spare (degraded until replacement) is documented, not hidden.

### Phase 5 — Secure Sharing and Access Control

- **Objective:** share files without exposing keys to the server, with controlled access.
- **Features:** public-key-based sharing; wrapped DEK distribution; time-limited access; download restrictions; device-bound permissions; revocation workflows.
- **Dependencies:** Phases 2 and 3 Completed; sharing/revocation semantics ADR Accepted.
- **Deliverable:** secure file sharing with controlled access.
- **Acceptance criteria (planning level):**
  - A recipient decrypts a shared file without the server seeing the DEK.
  - Expired or revoked grants are denied by the server; revoked recipients cannot obtain new versions.
  - Authorization is enforced independently of authentication; malicious-recipient scenarios have tests.
- **Honesty constraints to document:** revocation cannot retract data a recipient already decrypted; time limits and download restrictions are server-enforced policy rather than cryptographic guarantees unless a mechanism proven otherwise is adopted.

### Phase 6 — Recovery and Data Protection

- **Objective:** recoverability of both key access and stored data.
- **Features:** Shamir's Secret Sharing; threshold-based key recovery; immutable snapshots; file version restoration; secure deletion workflows; disaster recovery.
- **Dependencies:** Phases 2, 3 and 4 Completed; recovery-scheme ADR Accepted.
- **Deliverable:** recoverability of both encryption access and stored data.
- **Acceptance criteria (planning level):**
  - t-of-n shares recover access; fewer than t do not.
  - Recovery introduces no hidden server-side decryption capability (documented and tested).
  - Snapshot immutability tested; version restore tested.
  - A backup/restore drill is performed, with measured recovery time and data-loss window recorded.
  - Secure deletion semantics (key destruction versus blob deletion, and their limits) documented.

### Phase 7 — Security Intelligence

- **Objective:** detect and respond to attacks and tampering.
- **Features:** ransomware detection; suspicious-activity analysis; tamper-evident audit logs; signed audit checkpoints; security alerts; investigation and recovery workflows.
- **Dependencies:** Phases 1 and 3 Completed (audit hooks present since Phase 1); Phase 6 helpful for recovery workflows; audit-log ADR Accepted.
- **Deliverable:** security monitoring and attack-response capabilities.
- **Acceptance criteria (planning level):**
  - Audit-log modification, deletion and reordering are detected, and checkpoints verify offline.
  - Simulated attack scenarios run reproducibly with measured detection and false-positive rates.
  - Detection limits are documented: the server sees ciphertext, so signals are behavioural/metadata-based, or computed client-side.

### Phase 8 — Scalability and Observability

- **Objective:** measured scalability, reliability and performance.
- **Features:** performance optimization; Redis only if justified by measurements; asynchronous job processing only if PostgreSQL queue limits become relevant; Prometheus and Grafana; concurrent upload testing; load and failure testing; storage benchmarks (including an optional comparison against SeaweedFS native erasure coding).
- **Dependencies:** Phase 4 Completed; earlier phases as available.
- **Deliverable:** measured scalability, reliability and performance.
- **Acceptance criteria (planning level):**
  - Benchmarks have documented methodology, scripts and success thresholds defined before running.
  - Bottleneck report produced; any new technology cites the measurement that justified it.
  - Failure-testing results (node loss, repair under load) recorded.

### Phase 9 — Cloud Deployment and Production Hardening

- **Objective:** a deployable, demonstrable platform.
- **Features:** cloud deployment; SeaweedFS and S3-compatible adapters; multi-machine storage nodes; TLS and secrets management; backup and disaster recovery; security testing; documentation and final demonstrations.
- **Dependencies:** all previous phases Completed.
- **Deliverable:** deployable and demonstrable distributed storage platform.
- **Acceptance criteria (planning level):**
  - Each new adapter passes the Phase 1 `StorageNode` conformance suite.
  - Nodes run on separate machines with real failure domains; failure and repair demonstrated.
  - TLS everywhere between components that cross a network; secrets not stored in images or repositories.
  - Security testing (dependency scanning, API fuzzing, manual review checklist) results recorded.
  - Backup/restore drill repeated in the deployed environment.
  - Final documentation and demo script reproducible by a third party.

---

## 8. Lock-in guardrails and cross-phase risks

| Risk | Guardrail |
|---|---|
| Phase 0 choices constrain later phases | Phase 0 commits only to §6.1's committed column; every deferred technology has an owning phase and needs an ADR. |
| Phase 4 forces a schema rewrite | Phase 1 manifest/shard schema is codec-, stripe- and shard-index-aware from day one. |
| Retrofitting audit events in Phase 7 | Append-only audit-event recording starts in Phase 1; hash chaining and signing come in Phase 7. |
| Authentication scheme conflicts with zero-knowledge key derivation | ADR-0011 decided before Phase 1; auth secret kept separate from key-derivation material; auth hidden behind an internal interface. |
| Device registration precedes key management | Phase 1 stores device identity; public-key fields are populated and enforced in Phase 2. |
| Plaintext development path leaks into "production" | Config-gated, labelled dev-only, must be disabled by the Phase 2 gate; no zero-knowledge claims before then. |
| No client platform in the roadmap | ADR-0012 (browser SDK versus reference CLI) decided before Phase 2; `docs/architecture.md` marks the client as an open component. |
| Adapter drift (SeaweedFS/S3 behave differently) | One shared `StorageNode` conformance suite from Phase 1; adapters must pass it. |
| Simulated failure domains overstate durability | Claims register states the simulation until Phase 9. |
| Monitoring bolted on late | Structured logging and correlation IDs from Phase 0; Prometheus/Grafana in Phase 8 consume them. |
| Scope creep | Features not in this file require a change-log entry and approval. |

---

## 9. Open decisions register

| ID | Decision | Needed before | Status |
|---|---|---|---|
| D1 | PostgreSQL-only queue (`FOR UPDATE SKIP LOCKED`); defer Redis/RabbitMQ/Celery unless measurements justify | Phase 0 implementation | **Approved 2026-11-17** (ADR-0004) |
| D2 | Add `health()` to `StorageNode` | Phase 1 | Awaiting approval |
| D3 | Write quorum of 5 of 6 verified shards | Phase 4 | Awaiting approval |
| D4 | `zfec` as production codec (licence noted: GPLv2+ or TGPPL) plus optional reference codec | Phase 4 | Awaiting approval |
| D5 | Seventh spare node via Compose profile | Phase 4 | Roadmap lists as optional; confirm |
| D6 | Stripe = chunk = 4 MiB encrypted | Phase 3 | Awaiting approval |
| D7 | Python 3.12; `uv`; SQLAlchemy 2.x async API; `asyncpg` | Phase 0 implementation | **Approved 2026-11-17** (ADR-0013) |
| D8 | GitHub Actions for CI | Phase 0 implementation | **Approved 2026-11-17** (ADR-0013) |
| D9 | Integration tests on real PostgreSQL: Docker Compose locally, service container in CI; no SQLite | Task 0.7 | **Approved 2026-11-17** (ADR-0013) |
| D10 | Defer the worker process until the first real background job type | Phase 0 implementation | **Approved 2026-11-17** (ADR-0001) |
| D11 | Authentication scheme (ADR-0011) | Phase 1 | Open |
| D12 | Client platform and crypto libraries (ADR-0012) | Phase 2 | Open |
| D13 | Implementer defaults to confirm: PostgreSQL 16 pin; ruff, mypy, pytest-asyncio, httpx, pre-commit; gitleaks, pip-audit and lychee in CI | Phase 0 gate | Proposed (not in the approved list) |

---

## 10. Change log

| Date | Version | Change | Approved by |
|---|---|---|---|
| 2026-11-17 | 0.1 | Initial master plan created from the owner's Phase 0–9 roadmap; Phase 0 tasks 0.1–0.9 detailed; phases 1–9 at planning level; status model, ADR index, guardrails and decision register added. Phase 0 worker service proposed for deferral (D10). | Pending |
| 2026-11-17 | 0.2 | Owner approved D1, D7, D8, D9, D10; recorded in ADR-0001, ADR-0004 and ADR-0013 and in the decision register. Phase 0 moved to In progress with all tasks In progress (delivered, not yet run or merged). ADRs 0002, 0003, 0005-0010 drafted as Proposed. D2-D6, D11, D12 unchanged. D13 added for implementer defaults awaiting confirmation. Status model and acceptance criteria unchanged. | Owner (D1, D7-D10); remainder pending |
