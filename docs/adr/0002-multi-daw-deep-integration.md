# ADR 0002: Multi-DAW deep-integration doctrine

Status: Accepted

N0TE is DAW-independent. Every officially supported host targets `DEEP`; Ableton is only the first validated implementation and receives no permanent architectural privilege. `DETECTED_UNSUPPORTED`, `GENERIC`, and `ENHANCED` are implementation-maturity states, not runtime health states or final product ceilings.

Adapters expose universal concepts plus explicit host extensions. Session Clips, Logic regions/Live Loops cells, FL patterns/Playlist clips, and Pro Tools clips/playlists are not declared equivalent. If a safe native operation is unavailable, resolution proceeds through proven project mechanisms, native host mechanisms, characterized owned tools, N0TE/plugin/ARK orchestration, then Guided Manual.

Maturity and health are independent. Each fine-grained host capability records its integration depth and runtime state. A failing function degrades only that capability; aggregate adapter health is diagnostic and never suppresses healthy siblings. Job planning retains healthy native capabilities and resolves only missing functions through another implementation or Guided Manual. Only adapter-wide failures such as disconnection, protocol incompatibility, or lost workspace identity make the adapter unavailable.

Song identity, decisions, rights, versions, Creator projects, Notebook, Artist World, MARKs, knowledge, and recovery remain N0TE-owned above all workspaces. Capability failure and recovery must never change Song identity, maturity, or unrelated host functionality.

Host and adapter updates are capability-aware. Compatibility evidence is recorded per function as `VERIFIED`, `ASSUMED_COMPATIBLE`, `NEEDS_REVALIDATION`, `KNOWN_INCOMPATIBLE`, or `UNAVAILABLE`. Pending updates and aggregate health never blanket-disable healthy functions. Update recovery revalidates only affected paths, and circuit breakers open at capability scope unless the connection, protocol, process, or workspace identity has failed adapter-wide.
