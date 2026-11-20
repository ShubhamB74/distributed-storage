# ADR-0011: Authentication scheme

- **Status:** Accepted (D11 approved 2026-11-18)
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D11, D16, D17, ADR-0012 (client platform and crypto libraries), Phase 2 key hierarchy

## Context

Distributed Storage must authenticate users in Phase 1, before any client-side cryptography exists (Phase 2).
The scheme must not make the later zero-knowledge design impossible: the server must never learn
the secret from which file-encryption keys are derived, and one password must not serve as both a
server-verified credential and the root of the key hierarchy.

## Decision: Option A, a separated authentication secret

1. The server verifies an opaque, client-supplied `auth_secret`. It stores only an **Argon2id**
   verifier of it (random salt, parameters encoded in the hash string; library defaults reviewed
   against RFC 9106 guidance). Hashing runs off the event loop.
2. **Phase 1:** the secret is whatever the client sends (tests send random 32-byte values). There is
   no client-side derivation yet. Phase 1 accounts are development data and are **not migratable**
   to Phase 2; they are wiped when Phase 2 lands.
3. **Phase 2 (to be confirmed in ADR-0012 and the key-hierarchy ADR):** the client stretches the
   password with Argon2id, then derives two independent values with HKDF using distinct labels,
   for example `auth` (sent to the server as `auth_secret`) and `kek-root` (never leaves the
   client). The server therefore never receives key-derivation material.
4. Sessions: opaque random 256-bit bearer tokens, stored only as SHA-256 hashes, with absolute
   expiry, bound to a registered device, revocable (D16). No JWTs.
5. Abuse resistance without Redis: per-account failed-attempt counters with exponential backoff and
   a `locked_until` timestamp in PostgreSQL; identical responses and a dummy verification for
   unknown accounts, so existence is not revealed.
6. The Phase 2 client needs a per-user KDF salt before login. The endpoint serving it must return a
   deterministic fake value for unknown accounts, or it becomes an account-enumeration oracle.

## Alternatives considered

- **OPAQUE (RFC 9807).** Verified: published July 2025 by the IRTF CFRG as an *Informational*
  RFC (not an IETF standard); an augmented PAKE secure against pre-computation attacks that hides
  the password from the server, even during registration. Strongest option on paper: the server
  never holds a password-equivalent. Costs: multi-round protocol, client and server libraries whose
  maturity in Python and the chosen client platform is **unverified** (to assess in ADR-0012), and
  more moving parts before there is a client at all. Kept as a research experiment or a later
  upgrade; the credential verifier sits behind an interface so it can be swapped, although the
  login endpoints would change shape.
- **SRP.** Older aPAKE; weaker modern guidance and tooling; not preferred.
- **Server-side password hashing only (password sent to server).** Simplest, but the server sees
  the password; if that password also feeds key derivation, zero-knowledge is impossible. Rejected.
- **Passkeys / WebAuthn.** Good for authentication but does not by itself supply a key-derivation
  secret (the PRF extension would be required); a possible addition, not the base.

## Consequences

- Standard, reviewable primitives only; no custom protocol.
- `auth_secret` is a password-equivalent for *this service*: whoever sees it in transit (for
  example a TLS-terminating intermediary) can log in, but cannot derive file keys, assuming correct
  HKDF domain separation in Phase 2.
- A database leak allows offline guessing; cost per guess is the client-side Argon2id plus the
  server-side Argon2id.
- Argon2id verification is CPU and memory heavy: login is a denial-of-service surface, mitigated by
  lockout/backoff and, later, request rate limits.

## Revisit when

ADR-0012 shows a mature OPAQUE implementation for the chosen client platform, or the threat model
for intermediaries (TLS termination) requires that the server never see a password-equivalent.
