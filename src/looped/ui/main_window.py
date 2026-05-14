from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
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
from looped.services.waveform_service import WaveformService
from looped.ui.clip_editor_dialog import ClipEditorDialog
from looped.ui.formatting import format_ms

ALL_TRACKS_LABEL = "All Tracks"


class MainWindow(QMainWindow):
    def __init__(
        self,
        library_service: LibraryService,
        clip_service: ClipService,
        playlist_service: PlaylistService,
        waveform_service: WaveformService,
        audio_backend: AudioBackend,
    ) -> None:
        super().__init__()
        self.library_service = library_service
        self.clip_service = clip_service
        self.playlist_service = playlist_service
        self.waveform_service = waveform_service
        self.audio_backend = audio_backend

        self._all_tracks: list[Track] = []
        self._all_clips: list[Clip] = []
        self._tracks_by_row: dict[int, Track] = {}
        self._clips_by_id: dict[int, Clip] = {}
        self._playlists_by_id: dict[int, Playlist] = {}
        self._slider_is_user_dragging = False

        self.setWindowTitle("Looped MVP")
        self.resize(1340, 760)
        self._build_ui()

        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(100)
        self._playback_timer.timeout.connect(self._refresh_playback_position)
        self._playback_timer.start()

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
        splitter.setSizes([220, 820, 300])
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
        open_clip_editor_button = QPushButton("Open Clip Editor")
        open_clip_editor_button.clicked.connect(self.open_clip_editor_for_selected_track)
        toolbar.addWidget(import_button)
        toolbar.addWidget(add_to_playlist_button)
        toolbar.addWidget(delete_track_button)
        toolbar.addWidget(open_clip_editor_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        playback_row = QHBoxLayout()
        play_button = QPushButton("Play")
        play_button.clicked.connect(self.play_selected_track)
        pause_button = QPushButton("Pause")
        pause_button.clicked.connect(self.audio_backend.pause)
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self.stop_playback)
        self.repeat_checkbox = QCheckBox("Repeat Track")
        self.repeat_checkbox.toggled.connect(self.audio_backend.set_repeat_enabled)
        playback_row.addWidget(play_button)
        playback_row.addWidget(pause_button)
        playback_row.addWidget(stop_button)
        playback_row.addWidget(self.repeat_checkbox)
        playback_row.addStretch()
        layout.addLayout(playback_row)

        self.track_filter_input = QLineEdit()
        self.track_filter_input.setPlaceholderText("Filter tracks by title, artist, or album")
        self.track_filter_input.textChanged.connect(self.refresh_tracks)
        layout.addWidget(self.track_filter_input)

        self.track_table = QTableWidget(0, 5)
        self.track_table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", "Path"])
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.track_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.track_table.doubleClicked.connect(self.play_selected_track)
        self.track_table.itemSelectionChanged.connect(self._refresh_playback_position)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.track_table)

        seek_row = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_slider_released)
        self.seek_slider.valueChanged.connect(self._on_seek_slider_value_changed)
        self.duration_label = QLabel("0:00")
        seek_row.addWidget(self.position_label)
        seek_row.addWidget(self.seek_slider)
        seek_row.addWidget(self.duration_label)
        layout.addLayout(seek_row)
        return panel

    def _build_clips_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Saved Clips"))

        self.clip_filter_input = QLineEdit()
        self.clip_filter_input.setPlaceholderText("Filter clips by title or tags")
        self.clip_filter_input.textChanged.connect(self.refresh_clips)
        layout.addWidget(self.clip_filter_input)

        self.clip_list = QListWidget()
        self.clip_list.itemDoubleClicked.connect(self.play_selected_clip)
        layout.addWidget(self.clip_list)

        play_button = QPushButton("Play Clip")
        play_button.clicked.connect(self.play_selected_clip)
        edit_button = QPushButton("Edit Clip")
        edit_button.clicked.connect(self.open_clip_editor_for_selected_clip)
        delete_button = QPushButton("Delete Clip")
        delete_button.clicked.connect(self.delete_selected_clip)
        layout.addWidget(play_button)
        layout.addWidget(edit_button)
        layout.addWidget(delete_button)
        layout.addStretch()
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
        self._all_tracks = self.library_service.list_tracks(playlist_id=playlist_id)
        filter_text = self.track_filter_input.text().strip().lower()
        tracks = [
            track
            for track in self._all_tracks
            if not filter_text
            or filter_text in track.title.lower()
            or filter_text in track.artist.lower()
            or filter_text in track.album.lower()
        ]

        selected_track_id = self._selected_track_id()
        self._tracks_by_row = {row: track for row, track in enumerate(tracks)}
        self.track_table.setRowCount(len(tracks))

        for row, track in enumerate(tracks):
            values = [
                track.title,
                track.artist,
                track.album,
                format_ms(track.duration_ms),
                track.filepath,
            ]
            for column, value in enumerate(values):
                self.track_table.setItem(row, column, QTableWidgetItem(value))

        self.track_table.resizeColumnsToContents()
        self._update_track_scope_label()

        if selected_track_id is not None:
            self._select_track_by_id(selected_track_id)
        self._refresh_playback_position()

    def refresh_clips(self) -> None:
        self._all_clips = self.clip_service.list_clips()
        filter_text = self.clip_filter_input.text().strip().lower()
        clips = [
            clip
            for clip in self._all_clips
            if not filter_text or filter_text in clip.title.lower() or filter_text in clip.tags.lower()
        ]

        selected_clip_id = self._selected_clip_id()
        self._clips_by_id = {int(clip.id): clip for clip in clips if clip.id is not None}
        self.clip_list.clear()

        for clip in clips:
            source_track = self.library_service.get_track(clip.source_track_id)
            source_label = source_track.title if source_track else "Missing source"
            item = QListWidgetItem(f"{clip.title} [{source_label}] ({format_ms(clip.start_ms)} - {format_ms(clip.end_ms)})")
            item.setData(Qt.UserRole, int(clip.id))
            self.clip_list.addItem(item)

        if selected_clip_id is not None:
            self._select_clip_by_id(selected_clip_id)

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
        selected_name, accepted = QInputDialog.getItem(self, "Add To Playlist", "Playlist", names, 0, False)
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
        if not self._ensure_track_file_exists(track):
            return
        self.audio_backend.play_track(track)
        self._refresh_playback_position()

    def stop_playback(self) -> None:
        self.audio_backend.stop()
        self._refresh_playback_position(preview_position_ms=0)

    def play_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None:
            self._show_error("Select a clip first.")
            return

        track = self.library_service.get_track(clip.source_track_id)
        if track is None:
            self._show_error("The source track for this clip is missing.")
            return
        if not self._ensure_track_file_exists(track):
            return

        self.audio_backend.set_loop_region(clip.start_ms, clip.end_ms, enabled=False)
        self.audio_backend.play_clip(track, clip)
        self._refresh_playback_position(preview_position_ms=clip.start_ms)

    def open_clip_editor_for_selected_track(self) -> None:
        track = self._selected_track()
        if track is None:
            self._show_error("Select a track first.")
            return
        self._open_clip_editor(track, initial_clip_id=None)

    def open_clip_editor_for_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None:
            self._show_error("Select a clip first.")
            return
        track = self.library_service.get_track(clip.source_track_id)
        if track is None:
            self._show_error("The source track for this clip is missing.")
            return
        self._open_clip_editor(track, initial_clip_id=int(clip.id))

    def delete_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None or clip.id is None:
            self._show_error("Select a clip first.")
            return
        if QMessageBox.question(self, "Delete Clip", f"Delete clip '{clip.title}'?") != QMessageBox.Yes:
            return

        self.clip_service.delete_clip(int(clip.id))
        self.refresh_clips()

    def _open_clip_editor(self, track: Track, initial_clip_id: int | None) -> None:
        dialog = ClipEditorDialog(
            track=track,
            clip_service=self.clip_service,
            waveform_service=self.waveform_service,
            audio_backend=self.audio_backend,
            initial_clip_id=initial_clip_id,
            parent=self,
        )
        dialog.exec()
        self.refresh_clips()
        self.refresh_tracks()

    def _on_playlist_changed(self) -> None:
        self.refresh_tracks()

    def _refresh_playback_position(self, preview_position_ms: int | None = None) -> None:
        track = self._selected_track()
        if track is None:
            self.position_label.setText("0:00")
            self.duration_label.setText("0:00")
            self.seek_slider.setRange(0, 0)
            if not self._slider_is_user_dragging:
                self.seek_slider.setValue(0)
            return

        duration_ms = track.duration_ms
        position_ms = preview_position_ms if preview_position_ms is not None else 0

        if self.audio_backend.current_source_path() == track.filepath:
            duration_ms = self.audio_backend.current_duration_ms() or duration_ms
            position_ms = preview_position_ms if preview_position_ms is not None else self.audio_backend.current_position_ms()

        position_ms = max(0, min(position_ms, duration_ms or position_ms))
        self.position_label.setText(format_ms(position_ms))
        self.duration_label.setText(format_ms(duration_ms))

        if not self._slider_is_user_dragging:
            self.seek_slider.blockSignals(True)
            self.seek_slider.setRange(0, max(0, duration_ms))
            self.seek_slider.setValue(position_ms)
            self.seek_slider.blockSignals(False)

    def _on_seek_slider_pressed(self) -> None:
        self._slider_is_user_dragging = True

    def _on_seek_slider_value_changed(self, value: int) -> None:
        if self._slider_is_user_dragging:
            self.position_label.setText(format_ms(value))

    def _on_seek_slider_released(self) -> None:
        self._slider_is_user_dragging = False
        track = self._selected_track()
        if track is None:
            return
        if not self._ensure_track_file_exists(track):
            return
        self.audio_backend.play_track(track)
        self.audio_backend.seek(self.seek_slider.value())
        self._refresh_playback_position(preview_position_ms=self.seek_slider.value())

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

    def _selected_track_id(self) -> int | None:
        track = self._selected_track()
        return int(track.id) if track and track.id is not None else None

    def _selected_clip(self) -> Clip | None:
        clip_id = self._selected_clip_id()
        if clip_id is None:
            return None
        return self._clips_by_id.get(clip_id)

    def _selected_clip_id(self) -> int | None:
        item = self.clip_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.UserRole)
        return int(value) if value is not None else None

    def _select_playlist_by_id(self, playlist_id: int | None) -> None:
        for index in range(self.playlist_list.count()):
            item = self.playlist_list.item(index)
            value = item.data(Qt.UserRole)
            if value == playlist_id or (value is None and playlist_id is None):
                self.playlist_list.setCurrentRow(index)
                return

    def _select_track_by_id(self, track_id: int | None) -> bool:
        if track_id is None:
            return False
        for row, track in self._tracks_by_row.items():
            if track.id == track_id:
                self.track_table.selectRow(row)
                self.track_table.scrollToItem(self.track_table.item(row, 0))
                return True
        return False

    def _select_clip_by_id(self, clip_id: int | None) -> bool:
        if clip_id is None:
            return False
        for index in range(self.clip_list.count()):
            item = self.clip_list.item(index)
            if item.data(Qt.UserRole) == clip_id:
                self.clip_list.setCurrentRow(index)
                return True
        return False

    def _update_track_scope_label(self) -> None:
        playlist_id = self._selected_playlist_id()
        if playlist_id is None:
            self.track_scope_label.setText(ALL_TRACKS_LABEL)
            return
        playlist = self._playlists_by_id.get(playlist_id)
        self.track_scope_label.setText(playlist.name if playlist else ALL_TRACKS_LABEL)

    def _ensure_track_file_exists(self, track: Track) -> bool:
        if Path(track.filepath).exists():
            return True
        self._show_error(f"Track file is missing:\n{track.filepath}")
        return False

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Looped MVP", message)
