from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from looped.domain.models import Clip
from looped.persistence.repositories import ClipRepository, TrackRepository


class ClipService(ABC):
    @abstractmethod
    def create_clip(
        self,
        source_track_id: int,
        title: str,
        start_ms: int,
        end_ms: int,
        tags: str = "",
    ) -> Clip:
        raise NotImplementedError

    @abstractmethod
    def list_clips(self) -> list[Clip]:
        raise NotImplementedError

    @abstractmethod
    def get_clip(self, clip_id: int) -> Clip | None:
        raise NotImplementedError

    @abstractmethod
    def delete_clip(self, clip_id: int) -> None:
        raise NotImplementedError


class SqliteClipService(ClipService):
    def __init__(self, clip_repository: ClipRepository, track_repository: TrackRepository) -> None:
        self.clip_repository = clip_repository
        self.track_repository = track_repository

    def create_clip(
        self,
        source_track_id: int,
        title: str,
        start_ms: int,
        end_ms: int,
        tags: str = "",
    ) -> Clip:
        track = self.track_repository.get(source_track_id)
        if track is None:
            raise ValueError("Source track does not exist.")
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("Clip end time must be greater than start time.")
        if track.duration_ms and end_ms > track.duration_ms:
            raise ValueError("Clip end time cannot exceed the source track duration.")

        clip = Clip(
            id=None,
            source_track_id=source_track_id,
            title=title.strip() or f"{track.title} Clip",
            start_ms=start_ms,
            end_ms=end_ms,
            tags=tags.strip(),
            created_at=datetime.now(),
        )
        clip.id = self.clip_repository.create(clip)
        return clip

    def list_clips(self) -> list[Clip]:
        return self.clip_repository.list_all()

    def get_clip(self, clip_id: int) -> Clip | None:
        return self.clip_repository.get(clip_id)

    def delete_clip(self, clip_id: int) -> None:
        self.clip_repository.delete(clip_id)
