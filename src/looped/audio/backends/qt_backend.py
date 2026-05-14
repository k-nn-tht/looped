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
        self._clip_end_ms: int | None = None
        self._pending_seek_ms: int | None = None
        self._clip_guard_timer = QTimer()
        self._clip_guard_timer.setInterval(30)
        self._clip_guard_timer.timeout.connect(self._enforce_clip_end)
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)

    def play_track(self, track: Track) -> None:
        self._clip_end_ms = None
        self._pending_seek_ms = None
        self._clip_guard_timer.stop()
        self.player.setSource(QUrl.fromLocalFile(str(Path(track.filepath))))
        self.player.play()

    def play_clip(self, track: Track, clip: Clip) -> None:
        self._clip_end_ms = clip.end_ms
        self._pending_seek_ms = clip.start_ms
        self.player.setSource(QUrl.fromLocalFile(str(Path(track.filepath))))
        self.player.play()
        self._clip_guard_timer.start()

    def pause(self) -> None:
        self.player.pause()

    def stop(self) -> None:
        self._clip_end_ms = None
        self._pending_seek_ms = None
        self._clip_guard_timer.stop()
        self.player.stop()

    def seek(self, position_ms: int) -> None:
        if self.player.source().isEmpty():
            return
        self._pending_seek_ms = max(0, position_ms)
        self.player.setPosition(position_ms)

    def current_position_ms(self) -> int:
        return int(self.player.position())

    def current_duration_ms(self) -> int:
        return int(self.player.duration())

    def _enforce_clip_end(self) -> None:
        if self._clip_end_ms is None:
            return
        if self.player.position() >= self._clip_end_ms:
            self.stop()

    def _handle_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._pending_seek_ms is None:
            return
        if status in {QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia}:
            self.player.setPosition(self._pending_seek_ms)
            self._pending_seek_ms = None
