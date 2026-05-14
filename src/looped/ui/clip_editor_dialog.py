from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from looped.audio.backends.base import AudioBackend
from looped.domain.models import Clip, Track
from looped.services.clip_service import ClipService
from looped.services.waveform_service import WaveformService
from looped.ui.formatting import format_ms
from looped.ui.waveform_widget import WaveformWidget

DEFAULT_SPINBOX_MAX = 99_999_999


class ClipEditorDialog(QDialog):
    def __init__(
        self,
        track: Track,
        clip_service: ClipService,
        waveform_service: WaveformService,
        audio_backend: AudioBackend,
        initial_clip_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.track = track
        self.clip_service = clip_service
        self.waveform_service = waveform_service
        self.audio_backend = audio_backend
        self.initial_clip_id = initial_clip_id

        self._waveform_requested = False
        self._waveform_target_points = 800
        self._track_duration_ms = track.duration_ms
        self._editing_clip_id: int | None = None
        self._preview_active = False
        self._ignore_spinbox_updates = False
        self._slider_is_user_dragging = False
        self._clips_by_id: dict[int, Clip] = {}

        self.setWindowTitle(f"Clip Editor - {track.title}")
        self.resize(1180, 760)
        self.setModal(True)

        self._build_ui()
        self._set_clip_spinbox_bounds(self._track_duration_ms)
        self.waveform_service.waveform_ready.connect(self._handle_waveform_ready)

        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(100)
        self._playback_timer.timeout.connect(self._refresh_playback_position)
        self._playback_timer.start()

        self.refresh_clips()
        if self.initial_clip_id is not None and self._select_clip_by_id(self.initial_clip_id):
            pass
        else:
            self.clear_editor()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(f"{self.track.title}\n{self.track.artist or self.track.album or self.track.filepath}")
        header.setWordWrap(True)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_editor_panel())
        splitter.addWidget(self._build_clip_list_panel())
        splitter.setSizes([860, 320])
        layout.addWidget(splitter)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        waveform_group = QGroupBox("Waveform")
        waveform_layout = QVBoxLayout(waveform_group)

        self.waveform_status_label = QLabel("Waveform will load when the editor opens.")
        waveform_layout.addWidget(self.waveform_status_label)

        self.waveform_widget = WaveformWidget()
        self.waveform_widget.seek_requested.connect(self._seek_to_position)
        self.waveform_widget.clip_range_changed.connect(self._set_clip_range_from_waveform)
        waveform_layout.addWidget(self.waveform_widget)

        playback_controls = QHBoxLayout()
        play_track_button = QPushButton("Play Track")
        play_track_button.clicked.connect(self.play_track)
        preview_button = QPushButton("Preview Region")
        preview_button.clicked.connect(self.preview_region)
        pause_button = QPushButton("Pause")
        pause_button.clicked.connect(self.audio_backend.pause)
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self.stop_playback)
        self.loop_preview_checkbox = QCheckBox("Loop Preview")
        self.loop_preview_checkbox.toggled.connect(self._on_loop_preview_toggled)
        playback_controls.addWidget(play_track_button)
        playback_controls.addWidget(preview_button)
        playback_controls.addWidget(pause_button)
        playback_controls.addWidget(stop_button)
        playback_controls.addWidget(self.loop_preview_checkbox)
        playback_controls.addStretch()
        waveform_layout.addLayout(playback_controls)

        position_row = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_slider_released)
        self.seek_slider.valueChanged.connect(self._on_seek_slider_value_changed)
        self.duration_label = QLabel("0:00")
        position_row.addWidget(self.position_label)
        position_row.addWidget(self.seek_slider)
        position_row.addWidget(self.duration_label)
        waveform_layout.addLayout(position_row)

        marker_row = QHBoxLayout()
        set_start_button = QPushButton("Set Start To Current Position")
        set_start_button.clicked.connect(self.set_start_to_current_position)
        set_end_button = QPushButton("Set End To Current Position")
        set_end_button.clicked.connect(self.set_end_to_current_position)
        marker_row.addWidget(set_start_button)
        marker_row.addWidget(set_end_button)
        waveform_layout.addLayout(marker_row)

        layout.addWidget(waveform_group)

        editor_group = QGroupBox("Clip Details")
        editor_form = QFormLayout(editor_group)
        self.editor_state_label = QLabel("Creating a new clip")
        self.clip_title_input = QLineEdit()
        self.clip_tags_input = QLineEdit()
        self.clip_start_input = QSpinBox()
        self.clip_end_input = QSpinBox()
        for spinbox in (self.clip_start_input, self.clip_end_input):
            spinbox.setRange(0, DEFAULT_SPINBOX_MAX)
            spinbox.setSuffix(" ms")
            spinbox.setSingleStep(100)
            spinbox.valueChanged.connect(self._on_clip_range_inputs_changed)

        button_row = QHBoxLayout()
        save_button = QPushButton("Save New Clip")
        save_button.clicked.connect(self.create_clip)
        self.update_button = QPushButton("Update Clip")
        self.update_button.clicked.connect(self.update_clip)
        self.update_button.setEnabled(False)
        clear_button = QPushButton("Clear Editor")
        clear_button.clicked.connect(self.clear_editor)
        button_row.addWidget(save_button)
        button_row.addWidget(self.update_button)
        button_row.addWidget(clear_button)

        editor_form.addRow(self.editor_state_label)
        editor_form.addRow("Title", self.clip_title_input)
        editor_form.addRow("Tags", self.clip_tags_input)
        editor_form.addRow("Start", self.clip_start_input)
        editor_form.addRow("End", self.clip_end_input)
        editor_form.addRow(button_row)
        layout.addWidget(editor_group)
        return panel

    def _build_clip_list_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Clips For This Track"))

        self.clip_list = QListWidget()
        self.clip_list.currentItemChanged.connect(self._on_clip_selection_changed)
        self.clip_list.itemDoubleClicked.connect(self.play_selected_clip)
        layout.addWidget(self.clip_list)

        play_button = QPushButton("Play Saved Clip")
        play_button.clicked.connect(self.play_selected_clip)
        delete_button = QPushButton("Delete Clip")
        delete_button.clicked.connect(self.delete_selected_clip)
        layout.addWidget(play_button)
        layout.addWidget(delete_button)
        layout.addStretch()
        return panel

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._waveform_requested:
            return
        self._waveform_requested = True
        self._load_waveform()

    def closeEvent(self, event) -> None:
        self._playback_timer.stop()
        if self._preview_active and self._is_current_source_track():
            self.audio_backend.stop()
        self.audio_backend.set_loop_region(None, None, enabled=False)
        super().closeEvent(event)

    def refresh_clips(self) -> None:
        clips = self.clip_service.list_clips_for_track(int(self.track.id))
        selected_clip_id = self._selected_clip_id() or self._editing_clip_id
        self._clips_by_id = {int(clip.id): clip for clip in clips if clip.id is not None}
        self.clip_list.clear()
        for clip in clips:
            item = QListWidgetItem(f"{clip.title} ({format_ms(clip.start_ms)} - {format_ms(clip.end_ms)})")
            item.setData(Qt.UserRole, int(clip.id))
            self.clip_list.addItem(item)

        if selected_clip_id is not None:
            self._select_clip_by_id(selected_clip_id)

    def play_track(self) -> None:
        if not self._ensure_track_file_exists():
            return
        self._preview_active = False
        self.audio_backend.set_loop_region(None, None, enabled=False)
        self.audio_backend.play_track(self.track)
        self._refresh_playback_position()

    def preview_region(self) -> None:
        if not self._ensure_track_file_exists():
            return

        try:
            start_ms, end_ms = self._validated_range()
        except ValueError as exc:
            self._show_error(str(exc))
            return

        temp_clip = Clip(
            id=None,
            source_track_id=int(self.track.id),
            title=self.clip_title_input.text().strip() or f"{self.track.title} Preview",
            start_ms=start_ms,
            end_ms=end_ms,
            tags=self.clip_tags_input.text().strip(),
            hotkey=None,
            created_at=self.track.imported_at,
        )
        self._preview_active = True
        self.audio_backend.set_loop_region(start_ms, end_ms, enabled=self.loop_preview_checkbox.isChecked())
        self.audio_backend.play_clip(self.track, temp_clip)
        self._refresh_playback_position(preview_position_ms=start_ms)

    def stop_playback(self) -> None:
        self._preview_active = False
        self.audio_backend.set_loop_region(None, None, enabled=False)
        self.audio_backend.stop()
        self._refresh_playback_position(preview_position_ms=0)

    def create_clip(self) -> None:
        try:
            clip = self.clip_service.create_clip(
                source_track_id=int(self.track.id),
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

    def update_clip(self) -> None:
        if self._editing_clip_id is None:
            self._show_error("Select a saved clip to update.")
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

    def clear_editor(self) -> None:
        self._editing_clip_id = None
        self.clip_list.clearSelection()
        self.clip_title_input.clear()
        self.clip_tags_input.clear()
        self._ignore_spinbox_updates = True
        self.clip_start_input.setValue(0)
        default_end = min(self._track_duration_ms, 30_000) if self._track_duration_ms else 0
        self.clip_end_input.setValue(default_end)
        self._ignore_spinbox_updates = False
        self.update_button.setEnabled(False)
        self.editor_state_label.setText(f"Creating a new clip for {self.track.title}")
        self._preview_active = False
        self.audio_backend.set_loop_region(None, None, enabled=False)
        self._sync_waveform_clip_range()

    def set_start_to_current_position(self) -> None:
        position_ms = self._current_track_position()
        self.clip_start_input.setValue(min(position_ms, max(0, self.clip_end_input.value() - 1)))

    def set_end_to_current_position(self) -> None:
        position_ms = self._current_track_position()
        track_duration = self._resolved_duration_ms() or DEFAULT_SPINBOX_MAX
        self.clip_end_input.setValue(max(self.clip_start_input.value() + 1, min(position_ms, track_duration)))

    def play_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None:
            self._show_error("Select a clip first.")
            return
        if not self._ensure_track_file_exists():
            return
        self._preview_active = False
        self.audio_backend.set_loop_region(clip.start_ms, clip.end_ms, enabled=False)
        self.audio_backend.play_clip(self.track, clip)
        self._refresh_playback_position(preview_position_ms=clip.start_ms)

    def delete_selected_clip(self) -> None:
        clip = self._selected_clip()
        if clip is None or clip.id is None:
            self._show_error("Select a clip first.")
            return
        if QMessageBox.question(self, "Delete Clip", f"Delete clip '{clip.title}'?") != QMessageBox.Yes:
            return

        self.clip_service.delete_clip(int(clip.id))
        if self._editing_clip_id == int(clip.id):
            self.clear_editor()
        self.refresh_clips()

    def _load_waveform(self) -> None:
        if not Path(self.track.filepath).exists():
            self.waveform_status_label.setText("Track file is missing from disk.")
            self.waveform_widget.clear()
            return

        self.waveform_status_label.setText(f"Loading waveform for {Path(self.track.filepath).name}...")
        self.waveform_service.request_waveform(self.track.filepath, self._waveform_target_points)

    def _handle_waveform_ready(self, filepath: str, samples: list[float], error_message: str) -> None:
        if filepath != self.track.filepath:
            return

        if error_message:
            self.waveform_widget.set_waveform([], self._track_duration_ms)
            self.waveform_status_label.setText(error_message)
            return

        self.waveform_widget.set_waveform(samples, self._resolved_duration_ms())
        self.waveform_status_label.setText(f"Waveform loaded for {Path(filepath).name}")
        self._sync_waveform_clip_range()

    def _on_clip_selection_changed(self) -> None:
        clip = self._selected_clip()
        if clip is None:
            return
        self._editing_clip_id = int(clip.id) if clip.id is not None else None
        self.clip_title_input.setText(clip.title)
        self.clip_tags_input.setText(clip.tags)
        self._ignore_spinbox_updates = True
        self.clip_start_input.setValue(clip.start_ms)
        self.clip_end_input.setValue(clip.end_ms)
        self._ignore_spinbox_updates = False
        self.update_button.setEnabled(True)
        self.editor_state_label.setText(f"Editing clip '{clip.title}'")
        self._sync_waveform_clip_range()

    def _on_clip_range_inputs_changed(self) -> None:
        if self._ignore_spinbox_updates:
            return
        self._sync_waveform_clip_range()
        if self._preview_active and self._is_current_source_track():
            self.audio_backend.set_loop_region(
                self.clip_start_input.value(),
                self.clip_end_input.value(),
                enabled=self.loop_preview_checkbox.isChecked(),
            )

    def _set_clip_range_from_waveform(self, start_ms: int, end_ms: int) -> None:
        self._ignore_spinbox_updates = True
        self.clip_start_input.setValue(start_ms)
        self.clip_end_input.setValue(end_ms)
        self._ignore_spinbox_updates = False
        self._sync_waveform_clip_range()

    def _on_loop_preview_toggled(self, checked: bool) -> None:
        if not self._preview_active or not self._is_current_source_track():
            return
        self.audio_backend.set_loop_region(
            self.clip_start_input.value(),
            self.clip_end_input.value(),
            enabled=checked,
        )

    def _seek_to_position(self, position_ms: int) -> None:
        if not self._ensure_track_file_exists():
            return
        if not self._is_current_source_track():
            self._preview_active = False
            self.audio_backend.set_loop_region(None, None, enabled=False)
            self.audio_backend.play_track(self.track)
        self.audio_backend.seek(position_ms)
        self._refresh_playback_position(preview_position_ms=position_ms)

    def _refresh_playback_position(self, preview_position_ms: int | None = None) -> None:
        duration_ms = self._resolved_duration_ms()
        position_ms = preview_position_ms if preview_position_ms is not None else 0
        if self._is_current_source_track():
            duration_ms = self.audio_backend.current_duration_ms() or duration_ms
            position_ms = preview_position_ms if preview_position_ms is not None else self.audio_backend.current_position_ms()
            if duration_ms > self._track_duration_ms:
                self._track_duration_ms = duration_ms
                self._set_clip_spinbox_bounds(duration_ms)

        position_ms = max(0, min(position_ms, duration_ms or position_ms))
        self.position_label.setText(format_ms(position_ms))
        self.duration_label.setText(format_ms(duration_ms))
        self.waveform_widget.set_duration(duration_ms)
        self.waveform_widget.set_position(position_ms)

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
            self.waveform_widget.set_position(value)

    def _on_seek_slider_released(self) -> None:
        self._slider_is_user_dragging = False
        self._seek_to_position(self.seek_slider.value())

    def _sync_waveform_clip_range(self) -> None:
        self.waveform_widget.set_clip_range(self.clip_start_input.value(), self.clip_end_input.value())

    def _set_clip_spinbox_bounds(self, duration_ms: int) -> None:
        maximum = duration_ms if duration_ms > 0 else DEFAULT_SPINBOX_MAX
        self.clip_start_input.setMaximum(maximum)
        self.clip_end_input.setMaximum(maximum)

    def _validated_range(self) -> tuple[int, int]:
        start_ms = self.clip_start_input.value()
        end_ms = self.clip_end_input.value()
        if start_ms < 0:
            raise ValueError("Clip start time cannot be negative.")
        if end_ms <= start_ms:
            raise ValueError("Clip end time must be greater than start time.")
        track_duration = self._resolved_duration_ms()
        if track_duration and start_ms >= track_duration:
            raise ValueError("Clip start time must be within the source track duration.")
        if track_duration and end_ms > track_duration:
            raise ValueError("Clip end time cannot exceed the source track duration.")
        return start_ms, end_ms

    def _resolved_duration_ms(self) -> int:
        if not self._is_current_source_track():
            return self._track_duration_ms
        backend_duration = self.audio_backend.current_duration_ms()
        return backend_duration or self._track_duration_ms

    def _current_track_position(self) -> int:
        if not self._is_current_source_track():
            return 0
        return self.audio_backend.current_position_ms()

    def _is_current_source_track(self) -> bool:
        return self.audio_backend.current_source_path() == self.track.filepath

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

    def _select_clip_by_id(self, clip_id: int | None) -> bool:
        if clip_id is None:
            return False
        for index in range(self.clip_list.count()):
            item = self.clip_list.item(index)
            if item.data(Qt.UserRole) == clip_id:
                self.clip_list.setCurrentRow(index)
                return True
        return False

    def _ensure_track_file_exists(self) -> bool:
        if Path(self.track.filepath).exists():
            return True
        self._show_error(f"Track file is missing:\n{self.track.filepath}")
        return False

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Looped MVP", message)
