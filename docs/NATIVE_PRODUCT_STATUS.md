# Native product status

## Acceptance ladders

- Native N0TE gain, polarity, biquad, compressor, limiter, transient processing,
  and a lock-free single-producer/single-consumer audio ring are **SOURCE
  IMPLEMENTED**, **HOST COMPILED**, sanitizer checked, and native-unit tested on
  Linux x86_64. Listening and realtime device/host acceptance remain pending.
- VST3 hosting is not built. No legitimate SDK is present in the checkout and
  the build environment denied access to the official Steinberg repository.
  Metadata discovery must not be confused with module loading.
- Linux desktop/process discovery is executed on Linux. AppDir construction is
  fixture-validated and fails closed without a licensed private runtime input.
  `appimagetool`, PipeWire, JACK, ALSA development packages, and audio devices
  are absent in the current environment.
- Windows discovery/installer sources are fixture validated but not built on
  Windows. macOS build sources remain fixture validated but not target-run.

## Audio quality

The offline analyzer and DSP are numerically tested. The BS.1770 implementation
uses K-weighting and absolute/relative gating but has not passed the official
conformance vectors, so it is standards-conscious rather than certified.
True peak uses configurable windowed-sinc interpolation. No processor is marked
listening accepted or production accepted.
