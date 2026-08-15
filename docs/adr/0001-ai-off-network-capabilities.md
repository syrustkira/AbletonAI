# ADR 0001: AI OFF, network policy, and capability resolution

Status: Accepted (offline foundation; broader adapter migration remains partial)

## Decision

AI OFF is a real provider state and needs no credential. Component health uses the explicit states OFF, STARTING, READY, BUSY, DEGRADED, UNAVAILABLE, PAUSED, and RECOVERING. Network access from migrated N0TE networking paths is checked by a centralized fail-closed `NetworkPolicy`; OFFLINE permits loopback only. Capability resolution is typed/versioned and requires callers to opt into remote, metered, or mutation-authority implementations.

Reconnect changes availability only. It does not grant consent, select a paid/cloud fallback, synchronize, publish, or restore a public stream.

## Boundaries

This milestone migrates the AI provider router. Discovery and other networking paths must migrate before strict OFFLINE can be described as globally enforced. The capability registry is implemented and tested, but existing DAW/library integrations are not yet adapters. Gate 1 mutation authority is unchanged.
