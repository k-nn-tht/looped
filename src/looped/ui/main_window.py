from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from looped.audio.backends.base import AudioBackend
from looped.domain.models import Clip, Playlist, Track
from looped.services.clip_service import ClipService
from looped.services.library_service import LibraryService
from looped.services.playlist_service import PlaylistService

ALL_TRACKS_LABEL = "All Tracks"


def _format_ms(value: int) -> str:
    total_seconds = max(0, value // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


class MainWindow(QMainWindow):
    def __init__(
        self,
        library_service: LibraryService,
        clip_service: ClipService,
        playlist_service: PlaylistService,
        audio_backend: AudioBackend,
    ) -> None:
        super().__init__()
        self.library_service = library_service
        self.clip_service = clip_service
        self.playlist_service = playlist_service
        self.audio_backend = audio_backend
        self._tracks_by_row: dict[int, Track] = {}
        self._clips_by_row: dict[int, Clip] = {}
        self._playlists_by_id: dict[int, Playlist] = {}

        self.setWindowTitle("Looped MVP")
        self.resize(1280, 720)
        self._build_ui()
        self.refresh_playlists()
        self.refresh_tracks()
        self.refresh_clips()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_playlist_panel())
        splitter.addWidget(self._build_tracks_panel())
        splitter.addWidget(self._build_clips_panel())
        splitter.setSizes([220, 760, 300])
        layout.addWidget(splitter)

        self.setCentralWidget(root)

    def _build_playlist_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Playlists"))

        self.playlist_list = QListWidget()
        self.playlist_list.currentItemChanged.connect(self._on_playlist_changed)
        layout.addWidget(self.playlist_list)

        create_playlist_button = QPushButton("Create Playlist")
        create_playlist_button.clicked.connect(self.create_playlist)
        layout.addWidget(create_playlist_button)
        return panel

    def _build_tracks_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.track_scope_label = QLabel(ALL_TRACKS_LABEL)
        layout.addWidget(self.track_scope_label)

        toolbar = QHBoxLayout()
        import_button = QPushButton("Import Folder")
        import_button.clicked.connect(self.import_folder)
        add_to_playlist_button = QPushButton("Add To Playlist")
        add_to_playlist_button.clicked.connect(self.add_selected_tracks_to_playlist)
        delete_track_button = QPushButton("Delete Track")
        delete_track_button.clicked.connect(self.delete_selected_track)
        play_button = QPushButton("Play Track")
        play_button.clicked.connect(self.play_selected_track)
        pause_button = QPushButton("Pause")
        pause_button.clicked.connect(self.audio_backend.pause)
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self.audio_backend.stop)

        toolbar.addWidget(import_button)
        toolbar.addWidget(add_to_playlist_button)
        toolbar.addWidget(delete_track_button)
        toolbar.addStretch()
        toolbar.addWidget(play_button)
        toolbar.addWidget(pause_button)
        toolbar.addWidget(stop_button)
        layout.addLayout(toolbar)

        self.track_table = QTableWidget(0, 5)
        self.track_table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", "Path"])
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.track_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.track_table.doubleClicked.connect(self.play_selected_track)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.track_table)

        clip_group = QGroupBox("Create Clip")
        clip_form = QFormLayout(clip_group)
        self.clip_title_input = QLineEdit()
        self.clip_tags_input = QLineEdit()
        self.clip_start_input = QSpinBox()
        self.clip_end_input = QSpinBox()
        for spinbox in (self.clip_start_input, self.clip_end_input):
            spinbox.setRange(0, 99_999_999)
            spinbox.setSuffix(" ms")
            spinbox.setSingleStep(500)

        create_clip_button = QPushButton("Save Clip")
        create_clip_button.clicked.connect(self.create_clip)

        clip_form.addRow("Title", self.clip_title_input)
        clip_form.addRow("Tags", self.clip_tags_input)
        clip_form.addRow("Start", self.clip_start_input)
        clip_form.addRow("End", self.clip_end_input)
        clip_form.addRow(create_clip_button)
        layout.addWidget(clip_group)
        return panel

    def _build_clips_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Saved Clips"))

        self.clip_list = QListWidget()
        self.clip_list.itemDoubleClicked.connect(self.play_selected_clip)
        layout.addWidget(self.clip_list)

        play_clip_button = QPushButton("Play Clip")
        play_clip_button.clicked.connect(self.play_selected_clip)
        delete_clip_button = QPushButton("Delete Clip")
        delete_clip_button.clicked.connect(self.delete_selected_clip)
        layout.addWidget(play_clip_button)
        layout.addWidget(delete_clip_button)
        return panel

    def refresh_playlists(self) -> None:
        selected_playlist_id = self._selected_playlist_id()
        playlists = self.playlist_service.list_playlists()
        self._playlists_by_id = {int(playlist.id): playlist for playlist in playlists if playlist.id is not None}

        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()

        all_tracks_item = QListWidgetItem(ALL_TRACKS_LABEL)
        all_tracks_item.setData(Qt.UserRole, None)
        self.playlist_list.addItem(all_tracks_item)

        selected_row = 0
        for playlist in playlists:
            item = QListWidgetItem(playlist.name)
            item.setData(Qt.UserRole, int(playlist.id))
            self.playlist_list.addItem(item)
            if playlist.id == selected_playlist_id:
                selected_row = self.playlist_list.count() - 1

        self.playlist_list.setCurrentRow(selected_row)
        self.playlist_list.blockSignals(False)
        self._update_track_scope_label()

    def refresh_tracks(self) -> None:
        playlist_id = self._selected_playlist_id()
        tracks = self.library_service.list_tracks(playlist_id=playlist_id)
        self._tracks_by_row = {row: track for row, track in enumerate(tracks)}
        self.track_table.setRowCount(len(tracks))

        for row, track in enumerate(tracks):
            values = [
                track.title,
                track.artist,
                track.album,
                _format_ms(track.duration_ms),
                track.filepath,
            ]
            for column, value in enumerate(values):
                self.track_table.setItem(row, column, QTableWidgetItem(value))

        self.track_table.resizeColumnsToContents()
        self._update_track_scope_label()

    def refresh_clips(self) -> None:
        clips = self.clip_service.list_clips()
        self._clips_by_row = {row: clip for row, clip in enumerate(clips)}
        self.clip_list.clear()
        for row, clip in enumerate(clips):
            source_track = self.library_service.get_track(clip.source_track_id)
            source_label = source_track.title if source_track else "Missing source"
            item = QListWidgetItem(
                f"{clip.title} [{source_label}] ({_format_ms(clip.start_ms)} - {_format_ms(clip.end_ms)})"
            )
            item.setData(Qt.UserRole, row)
            self.clip_list.addItem(item)

    def import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose music folder")
        if not folder:
            return

        playlist_id = self._selected_playlist_id()
        imported = self.library_service.import_folder(Path(folder), playlist_id=playlist_id)
        self.refresh_tracks()
        self.refresh_clips()
        QMessageBox.information(self, "Import complete", f"Imported or updated {len(imported)} tracks.")

    def create_playlist(self) -> None:
        name, accepted = QInputDialog.getText(self, "Create Playlist", "Playlist name")
        if not accepted:
            return

        try:
            playlist = self.playlist_service.create_playlist(name)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.refresh_playlists()
        self._select_playlist_by_id(int(playlist.id))
        self.refresh_tracks()

    def add_selected_tracks_to_playlist(self) -> None:
        selected_tracks = self._selected_tracks()
        if not selected_tracks:
            self._show_error("Select one or more tracks first.")
            return

        playlists = self.playlist_service.list_playlists()
        if not playlists:
            self._show_error("Create a playlist before adding tracks to one.")
            return

        names = [playlist.name for playlist in playlists]
        selected_name, accepted = QInputDialog.getItem(
            self,
            "Add To Playlist",
            "Playlist",
            names,
            0,
            False,
        )
        if not accepted or not selected_name:
            return

        playlist = next((entry for entry in playlists if entry.name == selected_name), None)
        if playlist is None or playlist.id is None:
            self._show_error("Unable to load the selected playlist.")
            return

        added_count = self.playlist_service.add_tracks_to_playlist(
            int(playlist.id),
            [int(track.id) for track in selected_tracks if track.id is not None],
        )
        self.refresh_tracks()
        QMessageBox.information(self, "Tracks added", f"Added {added_count} track(s) to {playlist.name}.")

    def delete_selected_track(self) -> None:
        track = self._selected_track()
        if track is None or track.id is None:
            self._show_error("Select a track first.")
            return

        message = (
            f"Delete '{track.title}' from the library?\n\n"
            "This removes the database record, any playlist membership, and any saved clips for the track. "
            "The audio file on disk will not be deleted."
        )
        if QMessageBox.question(self, "Delete Track", message) != QMessageBox.Yes:
            return

        self.library_service.delete_track(int(track.id))
        self.refresh_tracks()
        self.refresh_clips()

    def play_selected_track(self) -> None:
        track = self._selected_track()
        if track is None:
            self._show_error("Select a track first.")
            return
        self.audio_backend.play_track(track)

    def create_clip(self) -> None:
        track = self._selected_track()
        if track is None or track.id is None:
            self._show_error("Select a source track before creating a clip.")
            return
        try:
            self.clip_service.create_clip(
                source_track_id=int(track.id),
                title=self.clip_title_input.text(),
                start_ms=self.clip_start_input.value(),
                end_ms=self.clip_end_input.value(),
                tags=self.clip_tags_input.text(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.clip_title_input.clear()
        self.clip_tags_input.clear()
        self.refresh_clips()

    def delete_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None or clip.id is None:
            self._show_error("Select a clip first.")
            return

        if QMessageBox.question(
            self,
            "Delete Clip",
            f"Delete clip '{clip.title}'?",
        ) != QMessageBox.Yes:
            return

        self.clip_service.delete_clip(int(clip.id))
        self.refresh_clips()

    def play_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None:
            self._show_error("Select a clip first.")
            return
        track = self.library_service.get_track(clip.source_track_id)
        if track is None:
            self._show_error("The source track for this clip is missing.")
            return
        self.audio_backend.play_clip(track, clip)

    def _on_playlist_changed(self) -> None:
        self.refresh_tracks()

    def _selected_playlist_id(self) -> int | None:
        item = self.playlist_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.UserRole)
        return int(value) if value is not None else None

    def _selected_track(self) -> Track | None:
        rows = self.track_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._tracks_by_row.get(rows[0].row())

    def _selected_tracks(self) -> list[Track]:
        rows = self.track_table.selectionModel().selectedRows()
        return [self._tracks_by_row[row.row()] for row in rows if row.row() in self._tracks_by_row]

    def _selected_clip(self) -> Clip | None:
        item = self.clip_list.currentItem()
        if item is None:
            return None
        row = item.data(Qt.UserRole)
        if row is None:
            return None
        return self._clips_by_row.get(int(row))

    def _select_playlist_by_id(self, playlist_id: int | None) -> None:
        for index in range(self.playlist_list.count()):
            item = self.playlist_list.item(index)
            value = item.data(Qt.UserRole)
            if value == playlist_id or (value is None and playlist_id is None):
                self.playlist_list.setCurrentRow(index)
                return

    def _update_track_scope_label(self) -> None:
        playlist_id = self._selected_playlist_id()
        if playlist_id is None:
            self.track_scope_label.setText(ALL_TRACKS_LABEL)
            return

        playlist = self._playlists_by_id.get(playlist_id)
        self.track_scope_label.setText(playlist.name if playlist else ALL_TRACKS_LABEL)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Looped MVP", message)
