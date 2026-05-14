from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from mutagen import File as MutagenFile

from looped.domain.models import Track
from looped.persistence.repositories import PlaylistRepository, TrackRepository

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


class LibraryService(ABC):
    @abstractmethod
    def import_folder(self, folder: Path, playlist_id: int | None = None) -> list[Track]:
        raise NotImplementedError

    @abstractmethod
    def list_tracks(self, playlist_id: int | None = None) -> list[Track]:
        raise NotImplementedError

    @abstractmethod
    def get_track(self, track_id: int) -> Track | None:
        raise NotImplementedError

    @abstractmethod
    def delete_track(self, track_id: int) -> None:
        raise NotImplementedError


class SqliteLibraryService(LibraryService):
    def __init__(
        self,
        track_repository: TrackRepository,
        playlist_repository: PlaylistRepository | None = None,
    ) -> None:
        self.track_repository = track_repository
        self.playlist_repository = playlist_repository

    def import_folder(self, folder: Path, playlist_id: int | None = None) -> list[Track]:
        imported_tracks: list[Track] = []
        imported_track_ids: list[int] = []
        for file_path in sorted(folder.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            track = self._build_track(file_path)
            track_id = self.track_repository.upsert(track)
            track.id = track_id
            imported_tracks.append(track)
            imported_track_ids.append(track_id)

        if playlist_id is not None:
            if self.playlist_repository is None:
                raise ValueError("Playlist support is not configured.")
            self.playlist_repository.add_tracks(playlist_id, imported_track_ids)
        return imported_tracks

    def list_tracks(self, playlist_id: int | None = None) -> list[Track]:
        if playlist_id is None:
            return self.track_repository.list_all()
        return self.track_repository.list_for_playlist(playlist_id)

    def get_track(self, track_id: int) -> Track | None:
        return self.track_repository.get(track_id)

    def delete_track(self, track_id: int) -> None:
        self.track_repository.delete(track_id)

    def _build_track(self, file_path: Path) -> Track:
        audio_file = MutagenFile(file_path)
        duration_ms = 0
        title = file_path.stem
        artist = ""
        album = ""

        if audio_file is not None:
            duration = getattr(getattr(audio_file, "info", None), "length", 0)
            duration_ms = int(float(duration) * 1000)
            tags = getattr(audio_file, "tags", None)
            if tags:
                title = self._read_first_tag(tags, ["TIT2", "title", "\xa9nam"], fallback=title)
                artist = self._read_first_tag(tags, ["TPE1", "artist", "\xa9ART"], fallback="")
                album = self._read_first_tag(tags, ["TALB", "album", "\xa9alb"], fallback="")

        return Track(
            id=None,
            filepath=str(file_path.resolve()),
            title=title,
            artist=artist,
            album=album,
            duration_ms=duration_ms,
            imported_at=datetime.now(),
        )

    @staticmethod
    def _read_first_tag(tags, keys: list[str], fallback: str) -> str:
        for key in keys:
            if key not in tags:
                continue
            value = tags[key]
            if isinstance(value, list) and value:
                return str(value[0])
            text = getattr(value, "text", None)
            if text:
                return str(text[0])
            return str(value)
        return fallback
