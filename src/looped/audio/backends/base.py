from __future__ import annotations

from abc import ABC, abstractmethod

from looped.domain.models import Clip, Track


class AudioBackend(ABC):
    @abstractmethod
    def play_track(self, track: Track) -> None:
        raise NotImplementedError

    @abstractmethod
    def play_clip(self, track: Track, clip: Clip) -> None:
        raise NotImplementedError

    @abstractmethod
    def pause(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def seek(self, position_ms: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def current_position_ms(self) -> int:
        raise NotImplementedError


class CaptureBackend(ABC):
    @abstractmethod
    def start_capture(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop_capture(self) -> None:
        raise NotImplementedError


class RoutingBackend(ABC):
    @abstractmethod
    def route_to_virtual_output(self, enabled: bool) -> None:
        raise NotImplementedError
