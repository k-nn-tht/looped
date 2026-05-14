from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from sqlite3 import IntegrityError

from looped.domain.models import Clip, Playlist, Track
from looped.persistence.playlist_item_repository import PlaylistItemRepository
from looped.persistence.repositories import ClipRepository, PlaylistRepository, TrackRepository


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

    @abstractmethod
    def add_clip_to_playlist(self, playlist_id: int, clip_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def remove_item(self, playlist_id: int, item_type: str, item_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_tracks_for_playlist(self, playlist_id: int) -> list[Track]:
        raise NotImplementedError

    @abstractmethod
    def list_clips_for_playlist(self, playlist_id: int) -> list[Clip]:
        raise NotImplementedError


class SqlitePlaylistService(PlaylistService):
    def __init__(
        self,
        playlist_repository: PlaylistRepository,
        playlist_item_repository: PlaylistItemRepository,
        track_repository: TrackRepository,
        clip_repository: ClipRepository,
    ) -> None:
        self.playlist_repository = playlist_repository
        self.playlist_item_repository = playlist_item_repository
        self.track_repository = track_repository
        self.clip_repository = clip_repository

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
        if self.playlist_repository.get(playlist_id) is None:
            raise ValueError("Selected playlist does not exist.")

        inserted = 0
        for track_id in dict.fromkeys(track_ids):
            if self.track_repository.get(track_id) is None:
                continue
            if self.playlist_item_repository.add_item(playlist_id, "track", track_id):
                inserted += 1
        return inserted

    def add_clip_to_playlist(self, playlist_id: int, clip_id: int) -> bool:
        if self.playlist_repository.get(playlist_id) is None:
            raise ValueError("Selected playlist does not exist.")
        if self.clip_repository.get(clip_id) is None:
            raise ValueError("Selected clip does not exist.")
        return self.playlist_item_repository.add_item(playlist_id, "clip", clip_id)

    def remove_item(self, playlist_id: int, item_type: str, item_id: int) -> None:
        self.playlist_item_repository.remove_item(playlist_id, item_type, item_id)

    def list_tracks_for_playlist(self, playlist_id: int) -> list[Track]:
        return self.playlist_item_repository.get_tracks_for_playlist(playlist_id)

    def list_clips_for_playlist(self, playlist_id: int) -> list[Clip]:
        return self.playlist_item_repository.get_clips_for_playlist(playlist_id)
