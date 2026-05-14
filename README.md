# Looped MVP

Looped is a local-first desktop audio app MVP for importing tracks, playing full songs, creating reusable clips, and replaying those clips from a soundboard-style list.

This first version is intentionally simple:

- Python is the main application layer.
- PySide6 provides the desktop UI and playback backend.
- SQLite stores track and clip metadata.
- Audio backend interfaces are separated so native C++ or platform-specific routing backends can be added later.

## Phase 1: Architecture And Repository Layout

### High-level architecture

- `UI (PySide6)`
  - Desktop window for importing folders, browsing tracks, playback controls, and clip management.
- `Service layer (Python)`
  - `LibraryService` scans folders, reads metadata, and manages track records.
  - `ClipService` creates and loads clip records.
- `Persistence layer (Python + SQLite)`
  - Repositories isolate SQL details from the rest of the app.
- `Audio backend abstraction`
  - `AudioBackend` defines playback behavior.
  - `QtAudioBackend` is the current implementation for fast MVP playback.
  - Future macOS/Windows capture and routing backends are stubbed behind separate interfaces.
- `Native audio core (future C++)`
  - Planned for low-latency playback, waveform generation, routing, and advanced audio features.
  - The Python layer is structured so a future `pybind11` module can replace or augment the MVP backend.

### Proposed repository structure

```text
Looped/
├── README.md
├── pyproject.toml
├── docs/
│   └── architecture.md
├── src/
│   └── looped/
│       ├── app.py
│       ├── audio/
│       │   └── backends/
│       │       ├── base.py
│       │       ├── qt_backend.py
│       │       └── routing_stubs.py
│       ├── db/
│       │   └── schema.sql
│       ├── domain/
│       │   └── models.py
│       ├── persistence/
│       │   ├── database.py
│       │   └── repositories.py
│       ├── services/
│       │   ├── clip_service.py
│       │   └── library_service.py
│       └── ui/
│           └── main_window.py
```

## Phase 2: MVP Data Model And Services

### Track model

- `id`
- `filepath`
- `title`
- `artist`
- `album`
- `duration_ms`
- `imported_at`

### Clip model

- `id`
- `source_track_id`
- `title`
- `start_ms`
- `end_ms`
- `tags`
- `created_at`

### SQLite schema notes

The MVP schema includes working tables for:

- `tracks`
- `clips`
- `playlists`
- `playlist_tracks`
- `settings`

Playlist and settings support are present as placeholders for later phases.

## Phase 3: Runnable MVP Prototype

Current MVP capabilities:

- Scan/import a folder of `mp3`, `wav`, `flac`, `m4a`, `aac`, `ogg`
- Read track metadata and persist it in SQLite
- List imported tracks
- Create playlists and filter the track table by playlist or `All Tracks`
- Add selected tracks to playlists
- Play/pause/stop selected tracks
- Resume playback with `Play` when the current track is paused
- Repeat the currently playing full track
- Seek selected tracks from the library playback slider
- Delete track records without deleting the underlying file
- Open a dedicated clip editor for a specific track
- Load waveform data lazily only when the clip editor opens
- Create clips from a selected track using start/end timestamps
- Adjust clip start/end visually from waveform handles in the clip editor
- Preview and loop the current clip region in the clip editor
- Replay saved clips
- Edit saved clips in the clip editor
- Delete saved clips
- Filter tracks and clips with simple text search

## Phase 4: Future Backend Stubs

The project includes stubs and TODO markers for:

- waveform preview
- hotkeys
- system-audio rolling buffer
- virtual audio output / call routing
- playlists UI
- BlackHole integration on macOS
- WASAPI loopback on Windows

## Phase 5: Setup And Run

### Requirements

- Python 3.11+
- macOS is the current target

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Run

```bash
python -m looped.app
```

### Notes

- The SQLite database is created at `looped.db` in the project root.
- Playback uses Qt Multimedia in the MVP.
- Clip replay seeks into the source file and stops automatically at the clip end.
- If metadata tags are missing, the file stem is used as the track title.
- Deleting a track uses SQLite foreign-key cascades to also remove dependent clips and playlist mappings. The source audio file on disk is kept.
- Importing into a selected playlist still imports into the master track library, then adds those imported tracks to the selected playlist.
- Waveform preview uses `audioread` to decode a lightweight downsampled envelope for local files and is only computed when the clip editor opens for a track.

## MVP implementation plan

1. Keep the first shipping path fully in Python so iteration stays fast.
2. Use repository and backend abstractions from day one so replacing internals is low-risk.
3. Add waveform generation and clip trimming UX after the basic import/play/save/replay loop is solid.
4. Introduce a C++ audio engine only when latency, routing, or decoding performance actually requires it.
