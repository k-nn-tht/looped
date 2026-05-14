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
    QStackedWidget,
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
from looped.ui.edit_track_dialog import EditTrackDialog
from looped.ui.formatting import format_ms
from looped.ui.track_table_widget import TrackTableWidget

LIBRARY_VIEW = "library"
SOUNDBOARD_VIEW = "soundboard"
ALL_TRACKS_LABEL = "All Tracks"
ALL_CLIPS_LABEL = "All Clips"


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

        self._current_view = LIBRARY_VIEW
        self._all_tracks: list[Track] = []
        self._all_clips: list[Clip] = []
        self._tracks_by_row: dict[int, Track] = {}
        self._clips_by_row: dict[int, Clip] = {}
        self._playlists_by_id: dict[int, Playlist] = {}
        self._slider_is_user_dragging = False

        self.setWindowTitle("Looped MVP")
        self.resize(1440, 820)
        self._build_ui()

        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(100)
        self._playback_timer.timeout.connect(self._refresh_playback_position)
        self._playback_timer.start()

        self.refresh_playlists()
        self.refresh_tracks()
        self.refresh_clips()
        self._switch_view(LIBRARY_VIEW)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        layout.addLayout(self._build_view_switcher())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_playlist_panel())
        splitter.addWidget(self._build_main_stack())
        splitter.setSizes([240, 1120])
        layout.addWidget(splitter)

        self.setCentralWidget(root)

    def _build_view_switcher(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.library_view_button = QPushButton("Library")
        self.library_view_button.setCheckable(True)
        self.library_view_button.clicked.connect(lambda: self._switch_view(LIBRARY_VIEW))
        self.soundboard_view_button = QPushButton("Soundboard")
        self.soundboard_view_button.setCheckable(True)
        self.soundboard_view_button.clicked.connect(lambda: self._switch_view(SOUNDBOARD_VIEW))
        row.addWidget(self.library_view_button)
        row.addWidget(self.soundboard_view_button)
        row.addStretch()
        return row

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

    def _build_main_stack(self) -> QWidget:
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self._build_library_view())
        self.view_stack.addWidget(self._build_soundboard_view())
        return self.view_stack

    def _build_library_view(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.track_scope_label = QLabel(ALL_TRACKS_LABEL)
        layout.addWidget(self.track_scope_label)

        toolbar = QHBoxLayout()
        import_button = QPushButton("Import Folder")
        import_button.clicked.connect(self.import_folder)
        edit_track_button = QPushButton("Edit Track")
        edit_track_button.clicked.connect(self.edit_selected_track)
        add_to_playlist_button = QPushButton("Add To Playlist")
        add_to_playlist_button.clicked.connect(self.add_selected_tracks_to_playlist)
        delete_track_button = QPushButton("Delete Track")
        delete_track_button.clicked.connect(self.delete_selected_track)
        open_clip_editor_button = QPushButton("Open Clip Editor")
        open_clip_editor_button.clicked.connect(self.open_clip_editor_for_selected_track)
        toolbar.addWidget(import_button)
        toolbar.addWidget(edit_track_button)
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

        self.track_table = TrackTableWidget(0, 5)
        self.track_table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", "Path"])
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.track_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.track_table.doubleClicked.connect(self.open_clip_editor_for_selected_track)
        self.track_table.itemSelectionChanged.connect(self._refresh_playback_position)
        self.track_table.paths_dropped.connect(self.import_dropped_paths)
        self.track_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.track_table)

        layout.addWidget(QLabel("Drag audio files or folders onto the track list to import"))

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

    def _build_soundboard_view(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.clip_scope_label = QLabel(ALL_CLIPS_LABEL)
        layout.addWidget(self.clip_scope_label)

        toolbar = QHBoxLayout()
        add_to_playlist_button = QPushButton("Add To Playlist")
        add_to_playlist_button.clicked.connect(self.add_selected_clip_to_playlist)
        play_button = QPushButton("Play Clip")
        play_button.clicked.connect(self.play_selected_clip)
        edit_button = QPushButton("Edit Clip")
        edit_button.clicked.connect(self.open_clip_editor_for_selected_clip)
        delete_button = QPushButton("Delete Clip")
        delete_button.clicked.connect(self.delete_selected_clip)
        toolbar.addWidget(add_to_playlist_button)
        toolbar.addWidget(play_button)
        toolbar.addWidget(edit_button)
        toolbar.addWidget(delete_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.clip_filter_input = QLineEdit()
        self.clip_filter_input.setPlaceholderText("Filter clips by title or tags")
        self.clip_filter_input.textChanged.connect(self.refresh_clips)
        layout.addWidget(self.clip_filter_input)

        self.clip_table = QTableWidget(0, 4)
        self.clip_table.setHorizontalHeaderLabels(["Clip", "Source Track", "Range", "Hotkey"])
        self.clip_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.clip_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.clip_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.clip_table.doubleClicked.connect(self.play_selected_clip)
        self.clip_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.clip_table)
        return panel

    def refresh_playlists(self) -> None:
        selected_playlist_id = self._selected_playlist_id()
        playlists = self.playlist_service.list_playlists()
        self._playlists_by_id = {int(playlist.id): playlist for playlist in playlists if playlist.id is not None}

        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()

        all_item = QListWidgetItem(self._all_items_label())
        all_item.setData(Qt.UserRole, None)
        self.playlist_list.addItem(all_item)

        selected_row = 0
        for playlist in playlists:
            item = QListWidgetItem(playlist.name)
            item.setData(Qt.UserRole, int(playlist.id))
            self.playlist_list.addItem(item)
            if playlist.id == selected_playlist_id:
                selected_row = self.playlist_list.count() - 1

        self.playlist_list.setCurrentRow(selected_row)
        self.playlist_list.blockSignals(False)
        self._update_scope_labels()

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
        if selected_track_id is not None:
            self._select_track_by_id(selected_track_id)
        self._update_scope_labels()
        self._refresh_playback_position()

    def refresh_clips(self) -> None:
        playlist_id = self._selected_playlist_id()
        self._all_clips = (
            self.clip_service.list_clips()
            if playlist_id is None
            else self.playlist_service.list_clips_for_playlist(playlist_id)
        )
        filter_text = self.clip_filter_input.text().strip().lower()
        clips = [
            clip
            for clip in self._all_clips
            if not filter_text or filter_text in clip.title.lower() or filter_text in clip.tags.lower()
        ]

        selected_clip_id = self._selected_clip_id()
        self._clips_by_row = {row: clip for row, clip in enumerate(clips)}
        self.clip_table.setRowCount(len(clips))

        for row, clip in enumerate(clips):
            source_track = self.library_service.get_track(clip.source_track_id)
            source_label = source_track.title if source_track else "Missing source"
            values = [
                clip.title,
                source_label,
                f"{format_ms(clip.start_ms)} - {format_ms(clip.end_ms)}",
                clip.hotkey or "",
            ]
            for column, value in enumerate(values):
                self.clip_table.setItem(row, column, QTableWidgetItem(value))

        self.clip_table.resizeColumnsToContents()
        if selected_clip_id is not None:
            self._select_clip_by_id(selected_clip_id)
        self._update_scope_labels()

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
        self.refresh_clips()

    def import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose music folder")
        if not folder:
            return
        self._import_paths([Path(folder)])

    def import_dropped_paths(self, path_strings: list[str]) -> None:
        self._import_paths([Path(path) for path in path_strings])

    def edit_selected_track(self) -> None:
        track = self._selected_track()
        if track is None or track.id is None:
            self._show_error("Select a track first.")
            return

        dialog = EditTrackDialog(track, self)
        if dialog.exec() == 0:
            return

        title, artist, album = dialog.values()
        try:
            self.library_service.update_track(int(track.id), title, artist, album)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.refresh_tracks()
        self.refresh_clips()
        self._select_track_by_id(int(track.id))

    def add_selected_tracks_to_playlist(self) -> None:
        selected_tracks = self._selected_tracks()
        if not selected_tracks:
            self._show_error("Select one or more tracks first.")
            return

        playlist = self._prompt_for_playlist("Add To Playlist", "Playlist")
        if playlist is None:
            return

        added_count = self.playlist_service.add_tracks_to_playlist(
            int(playlist.id),
            [int(track.id) for track in selected_tracks if track.id is not None],
        )
        self.refresh_tracks()
        QMessageBox.information(self, "Playlist", f"Added {added_count} track(s) to {playlist.name}.")

    def add_selected_clip_to_playlist(self) -> None:
        clip = self._selected_clip()
        if clip is None or clip.id is None:
            self._show_error("Select a clip first.")
            return

        playlist = self._prompt_for_playlist("Add To Playlist", "Playlist")
        if playlist is None:
            return

        try:
            added = self.playlist_service.add_clip_to_playlist(int(playlist.id), int(clip.id))
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.refresh_clips()
        message = f"Added clip to {playlist.name}." if added else f"Clip is already in {playlist.name}."
        QMessageBox.information(self, "Playlist", message)

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

    def delete_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None or clip.id is None:
            self._show_error("Select a clip first.")
            return
        if QMessageBox.question(self, "Delete Clip", f"Delete clip '{clip.title}'?") != QMessageBox.Yes:
            return

        self.clip_service.delete_clip(int(clip.id))
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

    def stop_playback(self) -> None:
        self.audio_backend.stop()
        self._refresh_playback_position(preview_position_ms=0)

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

    def _import_paths(self, paths: list[Path]) -> None:
        playlist_id = self._selected_playlist_id()
        imported = self.library_service.import_paths(paths, playlist_id=playlist_id)
        self.refresh_tracks()
        self.refresh_clips()
        QMessageBox.information(self, "Import complete", f"Imported or updated {len(imported)} tracks.")

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
        self.refresh_tracks()
        self.refresh_clips()

    def _prompt_for_playlist(self, title: str, label: str) -> Playlist | None:
        playlists = self.playlist_service.list_playlists()
        if not playlists:
            self._show_error("Create a playlist first.")
            return None

        names = [playlist.name for playlist in playlists]
        selected_name, accepted = QInputDialog.getItem(self, title, label, names, 0, False)
        if not accepted or not selected_name:
            return None
        return next((playlist for playlist in playlists if playlist.name == selected_name), None)

    def _switch_view(self, view_name: str) -> None:
        self._current_view = view_name
        self.library_view_button.setChecked(view_name == LIBRARY_VIEW)
        self.soundboard_view_button.setChecked(view_name == SOUNDBOARD_VIEW)
        self.view_stack.setCurrentIndex(0 if view_name == LIBRARY_VIEW else 1)
        self.refresh_playlists()
        self._update_scope_labels()

    def _on_playlist_changed(self) -> None:
        self.refresh_tracks()
        self.refresh_clips()

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
            position_ms = (
                preview_position_ms if preview_position_ms is not None else self.audio_backend.current_position_ms()
            )

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
        row = self.clip_table.currentRow()
        if row < 0:
            return None
        return self._clips_by_row.get(row)

    def _selected_clip_id(self) -> int | None:
        clip = self._selected_clip()
        return int(clip.id) if clip and clip.id is not None else None

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
                item = self.track_table.item(row, 0)
                if item is not None:
                    self.track_table.scrollToItem(item)
                return True
        return False

    def _select_clip_by_id(self, clip_id: int | None) -> bool:
        if clip_id is None:
            return False
        for row, clip in self._clips_by_row.items():
            if clip.id == clip_id:
                self.clip_table.selectRow(row)
                item = self.clip_table.item(row, 0)
                if item is not None:
                    self.clip_table.scrollToItem(item)
                return True
        return False

    def _all_items_label(self) -> str:
        return ALL_TRACKS_LABEL if self._current_view == LIBRARY_VIEW else ALL_CLIPS_LABEL

    def _update_scope_labels(self) -> None:
        playlist_id = self._selected_playlist_id()
        if playlist_id is None:
            self.track_scope_label.setText(ALL_TRACKS_LABEL)
            self.clip_scope_label.setText(ALL_CLIPS_LABEL)
            return
        playlist = self._playlists_by_id.get(playlist_id)
        label = playlist.name if playlist else self._all_items_label()
        self.track_scope_label.setText(label)
        self.clip_scope_label.setText(label)

    def _ensure_track_file_exists(self, track: Track) -> bool:
        if Path(track.filepath).exists():
            return True
        self._show_error(f"Track file is missing:\n{track.filepath}")
        return False

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Looped MVP", message)
