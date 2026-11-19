# Logging conventions

- One JSON object per line on stdout. Fields: `timestamp` (UTC, ms), `level`, `logger`, `event`,
  `service`, `env`, optional `request_id`, `correlation_id`, `fields`, `exception`.
- The log *message* is the event name in `snake_case`; data goes in `extra`:
  `logger.info("shard_stored", extra={"node_id": 3})`.
- `request_id` is generated server-side for every request. `correlation_id` is taken from
  `X-Correlation-ID` only if it matches `[A-Za-z0-9._-]{1,64}`; otherwise it equals the request ID.
- Redaction applies to `extra` fields: keys such as password, token, authorization, cookie,
  api key, private key, wrapped key, DEK/KEK, ciphertext and plaintext are masked, and raw
  `bytes` are logged as `<N bytes>`.
- **Redaction does not cover free text.** Never put secrets, keys, plaintext, ciphertext or
  personal data into messages or exception messages.
- Request bodies and query strings are never logged. Uvicorn access logs are disabled in favour
  of `http_request_completed`.
