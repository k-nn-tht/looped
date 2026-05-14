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
        hotkey: str | None = None,
    ) -> Clip:
        raise NotImplementedError

    @abstractmethod
    def list_clips(self) -> list[Clip]:
        raise NotImplementedError

    @abstractmethod
    def get_clip(self, clip_id: int) -> Clip | None:
        raise NotImplementedError

    @abstractmethod
    def list_clips_for_track(self, source_track_id: int) -> list[Clip]:
        raise NotImplementedError

    @abstractmethod
    def delete_clip(self, clip_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_clip(
        self,
        clip_id: int,
        title: str,
        start_ms: int,
        end_ms: int,
        tags: str = "",
        hotkey: str | None = None,
    ) -> Clip:
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
        hotkey: str | None = None,
    ) -> Clip:
        clip = self._validated_clip(
            clip_id=None,
            source_track_id=source_track_id,
            title=title,
            start_ms=start_ms,
            end_ms=end_ms,
            tags=tags,
            hotkey=hotkey,
        )
        clip.id = self.clip_repository.create(clip)
        return clip

    def update_clip(
        self,
        clip_id: int,
        title: str,
        start_ms: int,
        end_ms: int,
        tags: str = "",
        hotkey: str | None = None,
    ) -> Clip:
        existing_clip = self.clip_repository.get(clip_id)
        if existing_clip is None:
            raise ValueError("Clip does not exist.")

        clip = self._validated_clip(
            clip_id=clip_id,
            source_track_id=existing_clip.source_track_id,
            title=title,
            start_ms=start_ms,
            end_ms=end_ms,
            tags=tags,
            hotkey=hotkey if hotkey is not None else existing_clip.hotkey,
            created_at=existing_clip.created_at,
        )
        self.clip_repository.update(clip)
        return clip

    def list_clips(self) -> list[Clip]:
        return self.clip_repository.list_all()

    def get_clip(self, clip_id: int) -> Clip | None:
        return self.clip_repository.get(clip_id)

    def list_clips_for_track(self, source_track_id: int) -> list[Clip]:
        return self.clip_repository.list_for_track(source_track_id)

    def delete_clip(self, clip_id: int) -> None:
        self.clip_repository.delete(clip_id)

    def _validated_clip(
        self,
        clip_id: int | None,
        source_track_id: int,
        title: str,
        start_ms: int,
        end_ms: int,
        tags: str,
        hotkey: str | None,
        created_at: datetime | None = None,
    ) -> Clip:
        track = self.track_repository.get(source_track_id)
        if track is None:
            raise ValueError("Source track does not exist.")
        if start_ms < 0:
            raise ValueError("Clip start time cannot be negative.")
        if end_ms <= start_ms:
            raise ValueError("Clip end time must be greater than start time.")
        if track.duration_ms and start_ms >= track.duration_ms:
            raise ValueError("Clip start time must be within the source track duration.")
        if track.duration_ms and end_ms > track.duration_ms:
            raise ValueError("Clip end time cannot exceed the source track duration.")

        return Clip(
            id=clip_id,
            source_track_id=source_track_id,
            title=title.strip() or f"{track.title} Clip",
            start_ms=start_ms,
            end_ms=end_ms,
            tags=tags.strip(),
            hotkey=hotkey.strip() if hotkey else None,
            created_at=created_at or datetime.now(),
        )
