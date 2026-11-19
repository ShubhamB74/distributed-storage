# Fault-injection tests

Empty in Phase 0 by design. Fault-injection tests arrive with the storage engine
(coordinator crashes, node loss, corrupted shards). Convention: files here are
auto-marked `fault`; they may be slower and may need Docker. See `tests/README.md`.
