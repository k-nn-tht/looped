# Looped Architecture

## Design goals

- Fast MVP iteration for a solo developer
- Clean separation between application logic and audio backend details
- Easy migration path from a pure Python backend to a native C++ audio core
- Cross-platform boundaries defined early, with macOS-first implementation

## Python responsibilities

- UI and interaction flow
- Folder scanning and metadata extraction
- SQLite persistence
- Playback orchestration
- Clip CRUD logic
- Future integration point for native backends

## C++ responsibilities later

- Low-latency audio playback and mixing
- Clip triggering with tighter timing guarantees
- Waveform extraction
- Audio routing/capture engines
- Platform-specific high-performance output and device handling

## Suggested future native boundary

Use a Python-facing module such as `looped_native` exposed with `pybind11`:

- `AudioEngine`
- `ClipVoice`
- `WaveformExtractor`
- `RoutingController`

The Python service layer should continue to own:

- persistence
- app state
- UI models
- import workflows

## Why PySide6 for the MVP

- Reasonable desktop UX without building a web stack
- Built-in multimedia playback for a working first version
- Natural fit for future list/grid views and waveform widgets

## Audio backend strategy

Current backend:

- `QtAudioBackend`
  - Good enough for local playback and clip replay
  - Not intended as the final low-latency soundboard engine

Future backends:

- `CoreAudioRoutingBackend` for macOS output and virtual routing
- `WasapiRoutingBackend` for Windows output and loopback capture
- `NativeAudioBackend` for C++ playback/mixing
