# Storage nodes

A storage node is an independent, dumb blob store. The coordinator owns chunking, erasure coding, placement,
health policy, repair and integrity (ADR-0002). Nodes never replicate or interpret data.

## Interface (`distributed_storage.storage.base.StorageNode`)

| Method | Behaviour |
|---|---|
| `put(key, data)` | Durable when it returns. Write-once: identical bytes under an existing key is a no-op (`created=False`); different bytes raise `BlobConflictError`. Returns the length and SHA-256 the node computed. |
| `get(key)` | Returns the stored bytes or raises `BlobNotFoundError`. Does not verify them: callers compare with the SHA-256 recorded in PostgreSQL. |
| `head(key)` | `BlobInfo(length)` or `None`. |
| `delete(key)` | Idempotent; `True` if a blob was removed. |
| `health()` | `NodeHealth(healthy, detail, free_bytes)`; never raises for an unhealthy node. |

Keys are the shard placement's UUID in canonical lowercase form (ADR-0014); anything else raises
`InvalidBlobKeyError`, which is also what stops path traversal. Errors derive from `StorageError`;
I/O failures surface as `StorageUnavailableError` without leaking paths.

## LocalBlobStorage

- Layout: `<root>/blobs/<first two characters of the key>/<key>`; temporary files in `<root>/.tmp/`.
- Write path: write a temporary file, fsync, publish with `os.link` (atomic, refuses to overwrite),
  remove the temporary name, fsync the directory (POSIX only). A crash leaves either no blob or a complete
  blob; leftover temporary files are invisible and removed by `sweep_tmp`.
- Requires a file system with hard links. On Windows the directory fsync is skipped.
- Honest limit: whether the operating system honours fsync cannot be verified remotely (ADR-0008).
- Blocking I/O runs in worker threads; the default blob size limit is 64 MiB (the API enforces its own cap).

## Adding an adapter

Implement the protocol, then add its name and a factory to `ADAPTERS` and the `node` fixture in
`tests/unit/storage/conftest.py`. It must pass `test_storage_node_conformance.py` unchanged.
