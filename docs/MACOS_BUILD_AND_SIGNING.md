# macOS consumer build and release handoff

## Development staging

```bash
python3 scripts/build_macos_app.py --output build/macos --allow-missing-runtime
```

This creates **N0TE Development.app** and deterministic `dmg-root`. With no private runtime it is intentionally `consumer_ready=false` and exits with a visible development-build alert. A consumer-capable staging build requires a redistribution-approved universal2 or target-architecture CPython tree:

```bash
python3 scripts/build_macos_app.py --output build/macos --runtime-root /secure/build-inputs/cpython-macos-arm64
```

The input must place its executable at `bin/python3`; the builder installs it at `Contents/Frameworks/Python/bin/python3`. It is never downloaded and system Python is never used by the resulting app.

## Entitlements

The current portable Core needs no Apple entitlement, so `packaging/macos/entitlements.plist` is empty. Localhost and outbound connections are still governed by N0TE `NetworkPolicy`. Camera and microphone usage strings/entitlements must be added only with real native capture components and user-facing permission flows.

## Signing and notarization (external acceptance)

1. Build on the minimum supported macOS host with the approved private runtime.
2. Sign nested native libraries from inside out with the hardened runtime.
3. Sign the app using `codesign --force --deep --options runtime --entitlements packaging/macos/entitlements.plist --sign "Developer ID Application: …" "N0TE.app"`.
4. Verify with `codesign --verify --deep --strict --verbose=2 "N0TE.app"` and `spctl --assess --type execute --verbose=4 "N0TE.app"`.
5. Build the DMG with `scripts/build_unsigned_dmg.sh`, then sign the DMG.
6. Submit with `xcrun notarytool submit --wait`, staple with `xcrun stapler staple`, and reassess.

Credentials and private keys must remain in the release keychain/CI secret store and never enter this repository.
