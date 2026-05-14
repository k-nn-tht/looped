from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from looped.audio.backends.base import AudioBackend
from looped.domain.models import Clip, Track


class QtAudioBackend(AudioBackend):
    def __init__(self) -> None:
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        self._current_source_path: str | None = None
        self._pending_seek_ms: int | None = None
        self._repeat_enabled = False
        self._loop_region_enabled = False
        self._loop_start_ms: int | None = None
        self._loop_end_ms: int | None = None

        self._playback_guard_timer = QTimer()
        self._playback_guard_timer.setInterval(30)
        self._playback_guard_timer.timeout.connect(self._enforce_playback_rules)

        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)
        self.player.playbackStateChanged.connect(self._handle_playback_state_changed)

    def play_track(self, track: Track) -> None:
        source_path = str(Path(track.filepath))
        if (
            self._current_source_path == source_path
            and self.is_paused()
            and self._loop_start_ms is None
            and self._loop_end_ms is None
        ):
            self.resume()
            return

        if self._current_source_path != source_path:
            self.player.setSource(QUrl.fromLocalFile(source_path))
            self._current_source_path = source_path

        self.set_loop_region(None, None, enabled=False)
        self.player.play()
        self._playback_guard_timer.start()

    def play_clip(self, track: Track, clip: Clip) -> None:
        source_path = str(Path(track.filepath))
        if self._current_source_path != source_path:
            self.player.setSource(QUrl.fromLocalFile(source_path))
            self._current_source_path = source_path

        self.set_loop_region(clip.start_ms, clip.end_ms, enabled=self._loop_region_enabled)
        self._pending_seek_ms = clip.start_ms
        self.player.play()
        self._playback_guard_timer.start()

    def pause(self) -> None:
        self.player.pause()

    def resume(self) -> None:
        if self.player.source().isEmpty():
            return
        self.player.play()

    def stop(self) -> None:
        # Stop resets playback to the start of the current source so the next Play is predictable.
        self.player.stop()
        self._pending_seek_ms = 0
        self._playback_guard_timer.stop()
        if not self.player.source().isEmpty():
            self.player.setPosition(0)

    def seek(self, position_ms: int) -> None:
        if self.player.source().isEmpty():
            return
        self._pending_seek_ms = max(0, position_ms)
        self.player.setPosition(self._pending_seek_ms)

    def current_position_ms(self) -> int:
        return int(self.player.position())

    def current_duration_ms(self) -> int:
        return int(self.player.duration())

    def is_paused(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def current_source_path(self) -> str | None:
        return self._current_source_path

    def set_repeat_enabled(self, enabled: bool) -> None:
        self._repeat_enabled = enabled

    def set_loop_region(self, start_ms: int | None, end_ms: int | None, enabled: bool = False) -> None:
        if start_ms is None or end_ms is None or end_ms <= start_ms:
            self._loop_start_ms = None
            self._loop_end_ms = None
            self._loop_region_enabled = False
            return

        self._loop_start_ms = max(0, start_ms)
        self._loop_end_ms = max(self._loop_start_ms + 1, end_ms)
        self._loop_region_enabled = enabled
        self._playback_guard_timer.start()

    def _enforce_playback_rules(self) -> None:
        if not self.is_playing():
            return
        if self._loop_end_ms is None or self._loop_start_ms is None:
            return
        if self.player.position() < self._loop_end_ms:
            return

        if self._loop_region_enabled:
            self.player.setPosition(self._loop_start_ms)
            self.player.play()
            return

        self.stop()

    def _handle_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._pending_seek_ms is not None and status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            self.player.setPosition(self._pending_seek_ms)
            self._pending_seek_ms = None
            return

        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._repeat_enabled:
            self.player.setPosition(0)
            self.player.play()

    def _handle_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._playback_guard_timer.stop()
