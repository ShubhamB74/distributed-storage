# Threat model (stub)

**Status:** scope only. The full review is completed alongside Phase 2 and revisited per phase.

## Actors and scenarios to cover

Malicious storage administrators, compromised storage nodes, stolen credentials, compromised
client devices, malicious recipients, file tampering, replay, nonce reuse, key leakage,
metadata leakage, ransomware, insider threats, recovery attacks, denial of service.

## Baseline assumptions (to be refined)

- Storage nodes and the coordinator see ciphertext only (from Phase 2 onward). The coordinator
  performs erasure coding on ciphertext, so it sees full ciphertext and sizes.
- Phase 1 contains a development-only plaintext path with no confidentiality properties.
- Compose-based nodes share one host: failure domains are simulated.

## Out of scope for Phase 0

Cryptographic design, key lifecycle, sharing and recovery workflows (Phases 2, 5, 6).
