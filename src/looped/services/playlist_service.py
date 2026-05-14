from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from sqlite3 import IntegrityError

from looped.domain.models import Playlist
from looped.persistence.repositories import PlaylistRepository, TrackRepository


class PlaylistService(ABC):
    @abstractmethod
    def create_playlist(self, name: str) -> Playlist:
        raise NotImplementedError

    @abstractmethod
    def list_playlists(self) -> list[Playlist]:
        raise NotImplementedError

    @abstractmethod
    def get_playlist(self, playlist_id: int) -> Playlist | None:
        raise NotImplementedError

    @abstractmethod
    def add_tracks_to_playlist(self, playlist_id: int, track_ids: list[int]) -> int:
        raise NotImplementedError


class SqlitePlaylistService(PlaylistService):
    def __init__(self, playlist_repository: PlaylistRepository, track_repository: TrackRepository) -> None:
        self.playlist_repository = playlist_repository
        self.track_repository = track_repository

    def create_playlist(self, name: str) -> Playlist:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Playlist name is required.")

        playlist = Playlist(id=None, name=cleaned_name, created_at=datetime.now())
        try:
            playlist.id = self.playlist_repository.create(cleaned_name, playlist.created_at)
        except IntegrityError as exc:
            raise ValueError("A playlist with that name already exists.") from exc
        return playlist

    def list_playlists(self) -> list[Playlist]:
        return self.playlist_repository.list_all()

    def get_playlist(self, playlist_id: int) -> Playlist | None:
        return self.playlist_repository.get(playlist_id)

    def add_tracks_to_playlist(self, playlist_id: int, track_ids: list[int]) -> int:
        playlist = self.playlist_repository.get(playlist_id)
        if playlist is None:
            raise ValueError("Selected playlist does not exist.")

        valid_track_ids = [track_id for track_id in dict.fromkeys(track_ids) if self.track_repository.get(track_id)]
        if not valid_track_ids:
            return 0

        return self.playlist_repository.add_tracks(playlist_id, valid_track_ids)
