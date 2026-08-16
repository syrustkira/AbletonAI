# Network path audit

Runtime outbound paths are AI providers, Gemini native transport, sound
discovery, and updates. Each calls `NetworkPolicy.require` before transport.
The companion server's legacy structured OpenAI helper also performs an
explicit check before reading credentials or constructing transport.

Loopback sockets used by LiveBridge, the provider switchboard, health checks,
single-instance focus, and the companion UI are local IPC and remain allowed
in OFFLINE mode. They cannot target a caller-provided remote host.

`INSTALL_N0TE_MAC.command` and `INSTALL_N0TE_ABLETON_AI.py` are explicit
developer/bootstrap installers, not runtime callers. Their downloads require
the user's explicit install invocation. Consumer offline packages and private
runtimes do not execute these downloads. They remain separately auditable
bootstrap network paths and must not be invoked by the application updater.

There is no telemetry transport.
