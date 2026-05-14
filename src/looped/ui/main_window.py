from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
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
    QSlider,
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
from looped.services.waveform_service import WaveformService
from looped.ui.waveform_widget import WaveformWidget

ALL_TRACKS_LABEL = "All Tracks"
DEFAULT_SPINBOX_MAX = 99_999_999


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
        self._clips_by_row: dict[int, Clip] = {}
        self._playlists_by_id: dict[int, Playlist] = {}
        self._editing_clip_id: int | None = None
        self._editor_source_track_id: int | None = None
        self._playback_track_id: int | None = None
        self._playback_track_duration_ms = 0
        self._active_waveform_path: str | None = None
        self._ignore_clip_spinbox_updates = False
        self._slider_is_user_dragging = False

        self.setWindowTitle("Looped MVP")
        self.resize(1380, 820)
        self._build_ui()
        self._connect_signals()
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
        splitter.setSizes([220, 860, 320])
        layout.addWidget(splitter)

        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.waveform_service.waveform_ready.connect(self._handle_waveform_ready)

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
        self.track_table.itemSelectionChanged.connect(self._on_track_selection_changed)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.track_table)

        waveform_group = QGroupBox("Waveform Preview")
        waveform_layout = QVBoxLayout(waveform_group)

        self.waveform_status_label = QLabel("Select a track to load its waveform.")
        waveform_layout.addWidget(self.waveform_status_label)

        self.waveform_widget = WaveformWidget()
        self.waveform_widget.seek_requested.connect(self._seek_to_position)
        self.waveform_widget.clip_range_changed.connect(self._set_clip_range_from_waveform)
        waveform_layout.addWidget(self.waveform_widget)

        playback_row = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_slider_released)
        self.seek_slider.valueChanged.connect(self._on_seek_slider_value_changed)
        self.duration_label = QLabel("0:00")
        playback_row.addWidget(self.position_label)
        playback_row.addWidget(self.seek_slider)
        playback_row.addWidget(self.duration_label)
        waveform_layout.addLayout(playback_row)

        waveform_buttons = QHBoxLayout()
        set_start_button = QPushButton("Set Start To Current Position")
        set_start_button.clicked.connect(self.set_start_to_current_position)
        set_end_button = QPushButton("Set End To Current Position")
        set_end_button.clicked.connect(self.set_end_to_current_position)
        waveform_buttons.addWidget(set_start_button)
        waveform_buttons.addWidget(set_end_button)
        waveform_layout.addLayout(waveform_buttons)

        layout.addWidget(waveform_group)

        clip_group = QGroupBox("Clip Editor")
        clip_form = QFormLayout(clip_group)
        self.clip_editor_state_label = QLabel("Creating a new clip")
        self.clip_title_input = QLineEdit()
        self.clip_tags_input = QLineEdit()
        self.clip_start_input = QSpinBox()
        self.clip_end_input = QSpinBox()
        for spinbox in (self.clip_start_input, self.clip_end_input):
            spinbox.setRange(0, DEFAULT_SPINBOX_MAX)
            spinbox.setSuffix(" ms")
            spinbox.setSingleStep(100)
            spinbox.valueChanged.connect(self._on_clip_range_inputs_changed)

        clip_button_row = QHBoxLayout()
        create_clip_button = QPushButton("Save New Clip")
        create_clip_button.clicked.connect(self.create_clip)
        self.update_clip_button = QPushButton("Update Clip")
        self.update_clip_button.clicked.connect(self.update_clip)
        clear_clip_button = QPushButton("Clear Editor")
        clear_clip_button.clicked.connect(self.clear_clip_editor)
        clip_button_row.addWidget(create_clip_button)
        clip_button_row.addWidget(self.update_clip_button)
        clip_button_row.addWidget(clear_clip_button)

        clip_form.addRow(self.clip_editor_state_label)
        clip_form.addRow("Title", self.clip_title_input)
        clip_form.addRow("Tags", self.clip_tags_input)
        clip_form.addRow("Start", self.clip_start_input)
        clip_form.addRow("End", self.clip_end_input)
        clip_form.addRow(clip_button_row)
        layout.addWidget(clip_group)
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
        self.clip_list.currentItemChanged.connect(self._on_clip_selection_changed)
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
        self._all_tracks = self.library_service.list_tracks(playlist_id=playlist_id)
        track_filter = self.track_filter_input.text().strip().lower()
        tracks = [
            track
            for track in self._all_tracks
            if not track_filter
            or track_filter in track.title.lower()
            or track_filter in track.artist.lower()
            or track_filter in track.album.lower()
        ]

        selected_track_id = self._selected_track_id()
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

        if selected_track_id is not None:
            self._select_track_by_id(selected_track_id)

    def refresh_clips(self) -> None:
        self._all_clips = self.clip_service.list_clips()
        clip_filter = self.clip_filter_input.text().strip().lower()
        clips = [
            clip
            for clip in self._all_clips
            if not clip_filter or clip_filter in clip.title.lower() or clip_filter in clip.tags.lower()
        ]

        current_clip_id = self._editing_clip_id or self._selected_clip_id()
        self._clips_by_row = {row: clip for row, clip in enumerate(clips)}
        self.clip_list.clear()
        for row, clip in enumerate(clips):
            source_track = self.library_service.get_track(clip.source_track_id)
            source_label = source_track.title if source_track else "Missing source"
            item = QListWidgetItem(
                f"{clip.title} [{source_label}] ({_format_ms(clip.start_ms)} - {_format_ms(clip.end_ms)})"
            )
            item.setData(Qt.UserRole, int(clip.id))
            self.clip_list.addItem(item)

        if current_clip_id is not None:
            self._select_clip_by_id(current_clip_id)

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
        if self._editor_source_track_id == int(track.id):
            self.clear_clip_editor()
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
        self._playback_track_id = int(track.id) if track.id is not None else None
        self._playback_track_duration_ms = track.duration_ms

    def create_clip(self) -> None:
        track = self._editor_track()
        if track is None or track.id is None:
            self._show_error("Select a source track before creating a clip.")
            return

        try:
            clip = self.clip_service.create_clip(
                source_track_id=int(track.id),
                title=self.clip_title_input.text(),
                start_ms=self.clip_start_input.value(),
                end_ms=self.clip_end_input.value(),
                tags=self.clip_tags_input.text(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.refresh_clips()
        self._select_clip_by_id(int(clip.id))
        QMessageBox.information(self, "Clip saved", f"Saved clip '{clip.title}'.")

    def update_clip(self) -> None:
        if self._editing_clip_id is None:
            self._show_error("Select a saved clip first.")
            return

        try:
            clip = self.clip_service.update_clip(
                clip_id=self._editing_clip_id,
                title=self.clip_title_input.text(),
                start_ms=self.clip_start_input.value(),
                end_ms=self.clip_end_input.value(),
                tags=self.clip_tags_input.text(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.refresh_clips()
        self._select_clip_by_id(int(clip.id))
        QMessageBox.information(self, "Clip updated", f"Updated clip '{clip.title}'.")

    def clear_clip_editor(self) -> None:
        self._editing_clip_id = None
        self.clip_list.clearSelection()
        self.clip_title_input.clear()
        self.clip_tags_input.clear()
        self.clip_editor_state_label.setText("Creating a new clip")
        self.update_clip_button.setEnabled(False)

        track = self._selected_track()
        self._editor_source_track_id = int(track.id) if track and track.id is not None else None
        self._set_clip_spinbox_bounds(track.duration_ms if track else 0)

        self._ignore_clip_spinbox_updates = True
        self.clip_start_input.setValue(0)
        default_end = min(track.duration_ms, 30_000) if track and track.duration_ms else 0
        self.clip_end_input.setValue(default_end)
        self._ignore_clip_spinbox_updates = False
        self._sync_waveform_clip_range()
        self._update_editor_label()

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
        if self._editing_clip_id == int(clip.id):
            self.clear_clip_editor()
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
        if not self._ensure_track_file_exists(track):
            return
        self.audio_backend.play_clip(track, clip)
        self._playback_track_id = int(track.id) if track.id is not None else None
        self._playback_track_duration_ms = track.duration_ms

    def set_start_to_current_position(self) -> None:
        track = self._editor_track()
        if track is None:
            self._show_error("Select a track first.")
            return

        position_ms = self._current_track_position_for_editor()
        max_start = max(0, self.clip_end_input.value() - 1)
        self.clip_start_input.setValue(min(position_ms, max_start))

    def set_end_to_current_position(self) -> None:
        track = self._editor_track()
        if track is None:
            self._show_error("Select a track first.")
            return

        position_ms = self._current_track_position_for_editor()
        minimum_end = self.clip_start_input.value() + 1
        track_duration = track.duration_ms or DEFAULT_SPINBOX_MAX
        self.clip_end_input.setValue(max(minimum_end, min(position_ms, track_duration)))

    def _on_playlist_changed(self) -> None:
        self.refresh_tracks()

    def _on_track_selection_changed(self) -> None:
        track = self._selected_track()
        if track is None:
            self.waveform_status_label.setText("Select a track to load its waveform.")
            self.waveform_widget.clear()
            self._set_clip_spinbox_bounds(0)
            self.position_label.setText("0:00")
            self.duration_label.setText("0:00")
            self.seek_slider.setRange(0, 0)
            return

        if self._editing_clip_id is None:
            self._editor_source_track_id = int(track.id) if track.id is not None else None
            self._set_clip_spinbox_bounds(track.duration_ms)
            if self.clip_end_input.value() <= self.clip_start_input.value():
                default_end = min(track.duration_ms, 30_000) if track.duration_ms else 0
                self._ignore_clip_spinbox_updates = True
                self.clip_start_input.setValue(0)
                self.clip_end_input.setValue(default_end)
                self._ignore_clip_spinbox_updates = False
            self._sync_waveform_clip_range()

        self._load_waveform_for_track(track)
        self._refresh_playback_position()
        self._update_editor_label()

    def _on_clip_selection_changed(self) -> None:
        clip = self._selected_clip()
        if clip is None:
            if self._editing_clip_id is not None:
                self.clear_clip_editor()
            return
        self._load_clip_into_editor(clip)

    def _on_clip_range_inputs_changed(self) -> None:
        if self._ignore_clip_spinbox_updates:
            return
        self._sync_waveform_clip_range()

    def _on_seek_slider_pressed(self) -> None:
        self._slider_is_user_dragging = True

    def _on_seek_slider_value_changed(self, value: int) -> None:
        if self._slider_is_user_dragging:
            self.position_label.setText(_format_ms(value))
            self.waveform_widget.set_position(value)

    def _on_seek_slider_released(self) -> None:
        self._slider_is_user_dragging = False
        self._seek_to_position(self.seek_slider.value())

    def _seek_to_position(self, position_ms: int) -> None:
        track = self._selected_track()
        if track is None or track.id is None:
            self._show_error("Select a track first.")
            return
        if not self._ensure_track_file_exists(track):
            return
        if self._playback_track_id != int(track.id):
            self.audio_backend.play_track(track)
            self._playback_track_id = int(track.id)
            self._playback_track_duration_ms = track.duration_ms
        self.audio_backend.seek(position_ms)
        self._refresh_playback_position(preview_position_ms=position_ms)

    def _set_clip_range_from_waveform(self, start_ms: int, end_ms: int) -> None:
        self._ignore_clip_spinbox_updates = True
        self.clip_start_input.setValue(start_ms)
        self.clip_end_input.setValue(end_ms)
        self._ignore_clip_spinbox_updates = False
        self._sync_waveform_clip_range()

    def _handle_waveform_ready(self, filepath: str, samples: list[float], error_message: str) -> None:
        if filepath != self._active_waveform_path:
            return

        track = self._selected_track()
        duration_ms = track.duration_ms if track else 0
        if error_message:
            self.waveform_widget.set_waveform([], duration_ms)
            self.waveform_status_label.setText(error_message)
            return

        self.waveform_widget.set_waveform(samples, duration_ms)
        self.waveform_status_label.setText(f"Waveform loaded for {Path(filepath).name}")
        self._sync_waveform_clip_range()

    def _load_waveform_for_track(self, track: Track) -> None:
        self._active_waveform_path = track.filepath
        if not Path(track.filepath).exists():
            self.waveform_widget.clear()
            self.waveform_status_label.setText("Track file is missing from disk.")
            return
        self.waveform_widget.set_waveform([], track.duration_ms)
        self.waveform_status_label.setText(f"Loading waveform for {Path(track.filepath).name}...")
        self.waveform_service.request_waveform(track.filepath, target_points=600)

    def _load_clip_into_editor(self, clip: Clip) -> None:
        self._editing_clip_id = int(clip.id) if clip.id is not None else None
        self._editor_source_track_id = clip.source_track_id
        track = self.library_service.get_track(clip.source_track_id)

        self.update_clip_button.setEnabled(True)
        self._ignore_clip_spinbox_updates = True
        self.clip_title_input.setText(clip.title)
        self.clip_tags_input.setText(clip.tags)
        self.clip_start_input.setValue(clip.start_ms)
        self.clip_end_input.setValue(clip.end_ms)
        self._ignore_clip_spinbox_updates = False

        if track is not None and track.id is not None:
            self._focus_track(int(track.id))
            self._set_clip_spinbox_bounds(track.duration_ms)

        self._sync_waveform_clip_range()
        self._update_editor_label()

    def _focus_track(self, track_id: int) -> None:
        if not self._select_track_by_id(track_id):
            self._select_playlist_by_id(None)
            self.refresh_tracks()
            self._select_track_by_id(track_id)

    def _refresh_playback_position(self, preview_position_ms: int | None = None) -> None:
        selected_track = self._selected_track()
        if selected_track is None or selected_track.id is None:
            self.position_label.setText("0:00")
            self.duration_label.setText("0:00")
            self.seek_slider.setRange(0, 0)
            self.waveform_widget.set_position(0)
            return

        selected_track_id = int(selected_track.id)
        duration_ms = selected_track.duration_ms
        position_ms = 0
        if self._playback_track_id == selected_track_id:
            duration_ms = self.audio_backend.current_duration_ms() or duration_ms or self._playback_track_duration_ms
            position_ms = preview_position_ms if preview_position_ms is not None else self.audio_backend.current_position_ms()
            self._playback_track_duration_ms = duration_ms
        elif preview_position_ms is not None:
            position_ms = preview_position_ms

        duration_ms = max(0, duration_ms)
        position_ms = max(0, min(position_ms, duration_ms or position_ms))
        self.position_label.setText(_format_ms(position_ms))
        self.duration_label.setText(_format_ms(duration_ms))
        self.waveform_widget.set_duration(duration_ms)
        self.waveform_widget.set_position(position_ms)

        if not self._slider_is_user_dragging:
            self.seek_slider.blockSignals(True)
            self.seek_slider.setRange(0, max(0, duration_ms))
            self.seek_slider.setValue(position_ms)
            self.seek_slider.blockSignals(False)

    def _set_clip_spinbox_bounds(self, duration_ms: int) -> None:
        upper_bound = duration_ms if duration_ms > 0 else DEFAULT_SPINBOX_MAX
        self.clip_start_input.setMaximum(upper_bound)
        self.clip_end_input.setMaximum(upper_bound)

    def _sync_waveform_clip_range(self) -> None:
        self.waveform_widget.set_clip_range(self.clip_start_input.value(), self.clip_end_input.value())

    def _current_track_position_for_editor(self) -> int:
        track = self._editor_track()
        if track is None or track.id is None:
            return 0
        if self._playback_track_id != int(track.id):
            return 0
        return self.audio_backend.current_position_ms()

    def _editor_track(self) -> Track | None:
        if self._editor_source_track_id is not None:
            return self.library_service.get_track(self._editor_source_track_id)
        return self._selected_track()

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
        item = self.clip_list.currentItem()
        if item is None:
            return None
        clip_id = item.data(Qt.UserRole)
        if clip_id is None:
            return None
        return self.clip_service.get_clip(int(clip_id))

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

    def _update_editor_label(self) -> None:
        track = self._editor_track()
        track_title = track.title if track else "No track selected"
        if self._editing_clip_id is None:
            self.clip_editor_state_label.setText(f"Creating a new clip for {track_title}")
            self.update_clip_button.setEnabled(False)
            return
        self.clip_editor_state_label.setText(f"Editing saved clip for {track_title}")
        self.update_clip_button.setEnabled(True)

    def _ensure_track_file_exists(self, track: Track) -> bool:
        if Path(track.filepath).exists():
            return True
        self._show_error(f"Track file is missing:\n{track.filepath}")
        return False

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Looped MVP", message)
