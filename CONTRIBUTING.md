# Contributing

1. **IMPLEMENTATION_PLAN.md is the source of truth.** Update it in the same PR as the work it
   describes. Status only advances with evidence (see its section 2). Code written is not "completed".
2. **No silent architectural changes.** Architectural decisions need an ADR in `docs/adr/`
   (copy `0000-template.md`). Superseded ADRs are marked, never deleted.
3. **Tests ship with the code.** Unit tests for logic; integration tests (real PostgreSQL, never
   SQLite) for anything touching the database.
4. **No secrets in the repository.** Configuration comes from the environment or `*_FILE`
   secrets. CI runs a secret scan; pre-commit runs it locally.
5. **No security claim without evidence.** Add claims to `docs/security-claims.md` only with
   assumptions and a supporting test or experiment.
6. Before pushing: `make check`; with PostgreSQL up, `make test-integration`.
7. Keep future phases at planning level until they start; do not add dependencies owned by a
   later phase (see the plan's technology commitments).
