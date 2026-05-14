from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from mutagen import File as MutagenFile

from looped.domain.models import Track
from looped.persistence.playlist_item_repository import PlaylistItemRepository
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

    @abstractmethod
    def update_track(self, track_id: int, title: str, artist: str, album: str) -> Track:
        raise NotImplementedError

    @abstractmethod
    def import_paths(self, paths: list[Path], playlist_id: int | None = None) -> list[Track]:
        raise NotImplementedError


class SqliteLibraryService(LibraryService):
    def __init__(
        self,
        track_repository: TrackRepository,
        playlist_repository: PlaylistRepository | None = None,
        playlist_item_repository: PlaylistItemRepository | None = None,
    ) -> None:
        self.track_repository = track_repository
        self.playlist_repository = playlist_repository
        self.playlist_item_repository = playlist_item_repository

    def import_folder(self, folder: Path, playlist_id: int | None = None) -> list[Track]:
        return self.import_paths([folder], playlist_id=playlist_id)

    def list_tracks(self, playlist_id: int | None = None) -> list[Track]:
        if playlist_id is None:
            return self.track_repository.list_all()
        if self.playlist_item_repository is not None:
            return self.playlist_item_repository.get_tracks_for_playlist(playlist_id)
        return self.track_repository.list_for_playlist(playlist_id)

    def get_track(self, track_id: int) -> Track | None:
        return self.track_repository.get(track_id)

    def delete_track(self, track_id: int) -> None:
        self.track_repository.delete(track_id)

    def update_track(self, track_id: int, title: str, artist: str, album: str) -> Track:
        track = self.track_repository.get(track_id)
        if track is None:
            raise ValueError("Track does not exist.")

        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Track title is required.")

        self.track_repository.update_metadata(
            track_id=track_id,
            title=cleaned_title,
            artist=artist.strip(),
            album=album.strip(),
        )
        updated_track = self.track_repository.get(track_id)
        if updated_track is None:
            raise ValueError("Unable to reload the updated track.")
        return updated_track

    def import_paths(self, paths: list[Path], playlist_id: int | None = None) -> list[Track]:
        imported_tracks: list[Track] = []
        imported_track_ids: list[int] = []

        for file_path in self._iter_supported_files(paths):
            track = self._build_track(file_path)
            track_id = self.track_repository.upsert(track)
            track.id = track_id
            imported_tracks.append(track)
            imported_track_ids.append(track_id)

        if playlist_id is not None:
            if self.playlist_item_repository is not None:
                for track_id in imported_track_ids:
                    self.playlist_item_repository.add_item(playlist_id, "track", track_id)
            elif self.playlist_repository is None:
                raise ValueError("Playlist support is not configured.")
            else:
                self.playlist_repository.add_tracks(playlist_id, imported_track_ids)
        return imported_tracks

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
    def _iter_supported_files(paths: list[Path]) -> list[Path]:
        files: set[Path] = set()
        for path in paths:
            resolved_path = path.resolve()
            if resolved_path.is_dir():
                for file_path in resolved_path.rglob("*"):
                    if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files.add(file_path.resolve())
                continue

            if resolved_path.is_file() and resolved_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.add(resolved_path)

        return sorted(files)

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
