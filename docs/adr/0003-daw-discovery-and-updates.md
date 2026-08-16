# ADR 0003: Shared DAW discovery and component-aware updates

Status: Accepted

N0TE uses one `DawDiscoveryService` for first-run **Detect DAWs**, startup, Settings, Diagnostics, and update compatibility evaluation. Installations are identified independently from Songs, multiple versions may coexist, detection does not imply support, and every official host targets DEEP maturity. Ableton is the only currently available real adapter.

Updates are component-aware, transactional at the distribution boundary, and governed by a separate update authority. Remote checking and payload access obey `NetworkPolicy`; OFFLINE is a healthy paused state. Manually imported signed `.n0teupdate` packages require no network. Release authenticity signatures and payload hashes are separate checks. Production release keys are external build inputs and are never fabricated in source.

DAW adapter updates declare fixed, revalidation-required, and unchanged capabilities. Pending updates and aggregate health never suppress healthy capabilities. Loaded host/native components wait for host close without terminating the DAW. Application rollback restores application components only and never performs project Undo or changes Song identity, AI mode, Network mode, Community state, or privacy policy.
