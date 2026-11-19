# ADR-0010: Node failure detection and repair grace periods

- **Status:** Proposed
- **Date:** 2026-11-17
- **Related:** ADR-0006, ADR-0007

## Decision (proposed)

- A lease-holding prober calls `health()` every few seconds; real PUT/GET failures feed the same counters.
- States `healthy -> suspect -> down -> retired` with hysteresis (several consecutive failures to degrade, several successes to recover).
- "Down" is distinct from "repair": repair starts only after a configurable grace period (default about 10 minutes) to avoid repair storms during restarts.
- A single detector is a deliberate simplification; gossip/SWIM is out of scope.
