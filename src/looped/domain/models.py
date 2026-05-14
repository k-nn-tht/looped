from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Track:
    id: int | None
    filepath: str
    title: str
    artist: str
    album: str
    duration_ms: int
    imported_at: datetime


@dataclass(slots=True)
class Clip:
    id: int | None
    source_track_id: int
    title: str
    start_ms: int
    end_ms: int
    tags: str
    hotkey: str | None
    created_at: datetime


@dataclass(slots=True)
class Playlist:
    id: int | None
    name: str
    created_at: datetime
