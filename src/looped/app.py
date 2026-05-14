from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from looped.audio.backends.qt_backend import QtAudioBackend
from looped.persistence.database import Database
from looped.persistence.playlist_item_repository import PlaylistItemRepository
from looped.persistence.repositories import ClipRepository, PlaylistRepository, TrackRepository
from looped.services.clip_service import SqliteClipService
from looped.services.library_service import SqliteLibraryService
from looped.services.playlist_service import SqlitePlaylistService
from looped.services.waveform_service import WaveformService
from looped.ui.main_window import MainWindow


def build_application() -> MainWindow:
    project_root = Path.cwd()
    database = Database(project_root / "looped.db")
    database.initialize()

    track_repository = TrackRepository(database)
    clip_repository = ClipRepository(database)
    playlist_item_repository = PlaylistItemRepository(database)
    playlist_repository = PlaylistRepository(database)
    library_service = SqliteLibraryService(track_repository, playlist_repository, playlist_item_repository)
    clip_service = SqliteClipService(clip_repository, track_repository)
    playlist_service = SqlitePlaylistService(
        playlist_repository,
        playlist_item_repository,
        track_repository,
        clip_repository,
    )
    waveform_service = WaveformService()
    audio_backend = QtAudioBackend()
    # TODO: Register the future global hotkey listener here once clip hotkey binding is implemented.

    return MainWindow(
        library_service=library_service,
        clip_service=clip_service,
        playlist_service=playlist_service,
        waveform_service=waveform_service,
        audio_backend=audio_backend,
    )


def main() -> int:
    application = QApplication(sys.argv)
    window = build_application()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
