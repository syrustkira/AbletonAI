# Third-party components and source context

## N0TE / original AbletonAI lineage

Original repository: `syrustkira/AbletonAI`
License: GPL-3.0

N0TE's project history began from this GPL-3.0 repository and was substantially modified/expanded. The package includes `LICENSE` and `MODIFICATIONS.md` and ships source form for the N0TE application contained in the bundle.

## Ableton Live MCP bridge

Repository: `bschoepke/ableton-live-mcp`
Pinned commit: `70f7df9192b78d9bd9405f369c9e046c88f1610e`
License: MIT
Expected core bridge Git blob SHA-1: `ecc4fd7945ea748582b0534bf5ea119a878933eb`

The installer downloads the pinned source from GitHub at install time, verifies the expected commit layout and core bridge blob, and copies the upstream MIT license alongside the installed Remote Script and into N0TE's third-party license directory. N0TE does not claim authorship of the upstream Ableton bridge or AgentAudioTap.

## Python prerequisite

When no suitable Python is present, the macOS bootstrap can install the official Python.org Python 3.13.15 package after explicit user approval. The package checksum and Python Software Foundation signing identity (Apple Developer ID BMM5U3QVKW) are verified before system installation. Python itself is distributed under the Python Software Foundation License; N0TE does not bundle the Python installer payload inside this ZIP.

## Openverse

N0TE can query the public Openverse audio API as an optional web-discovery provider. Results retain source/license/provenance fields supplied by the API.

## Freesound

N0TE can query the Freesound API when the user supplies a key. Search/preview integration does not imply that every result is cleared for every use; preserve returned license/source information. Original-file download/OAuth is not automated in this build.

## OpenAI API

N0TE communicates with the OpenAI Responses API using the user's own API key. API keys are not included in the bundle and API billing is separate from a ChatGPT subscription.
