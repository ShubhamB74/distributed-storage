"""Errors raised by storage nodes (ADR-0002)."""


class StorageError(Exception):
    """Base class for all storage-node errors."""


class InvalidBlobKeyError(StorageError, ValueError):
    """The key is not a canonical lowercase UUID."""


class BlobNotFoundError(StorageError):
    """No blob exists under the key."""


class BlobConflictError(StorageError):
    """Blobs are write-once: the key already holds different content (ADR-0014)."""


class BlobTooLargeError(StorageError):
    """The blob exceeds the node's size limit."""


class StorageUnavailableError(StorageError):
    """The node could not complete the operation because of an I/O failure."""
