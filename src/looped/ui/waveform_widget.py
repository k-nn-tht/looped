from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    seek_requested = Signal(int)
    clip_range_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[float] = []
        self._duration_ms = 0
        self._position_ms = 0
        self._clip_start_ms = 0
        self._clip_end_ms = 0
        self._drag_mode: str | None = None
        self.setMinimumHeight(180)

    def set_waveform(self, samples: list[float], duration_ms: int) -> None:
        self._samples = samples
        self._duration_ms = max(0, duration_ms)
        self.update()

    def set_duration(self, duration_ms: int) -> None:
        self._duration_ms = max(0, duration_ms)
        self.update()

    def set_position(self, position_ms: int) -> None:
        self._position_ms = max(0, position_ms)
        self.update()

    def set_clip_range(self, start_ms: int, end_ms: int) -> None:
        self._clip_start_ms = max(0, start_ms)
        self._clip_end_ms = max(self._clip_start_ms, end_ms)
        self.update()

    def clear(self) -> None:
        self._samples = []
        self._duration_ms = 0
        self._position_ms = 0
        self._clip_start_ms = 0
        self._clip_end_ms = 0
        self._drag_mode = None
        self.update()

    def paintEvent(self, _: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#f3f4f6"))

        center_y = self.height() / 2
        painter.setPen(QPen(QColor("#d1d5db"), 1))
        painter.drawLine(0, int(center_y), self.width(), int(center_y))

        if self._duration_ms > 0 and self._clip_end_ms > self._clip_start_ms:
            start_x = self._ms_to_x(self._clip_start_ms)
            end_x = self._ms_to_x(self._clip_end_ms)
            painter.fillRect(int(start_x), 0, max(1, int(end_x - start_x)), self.height(), QColor(147, 197, 253, 70))
            painter.setPen(QPen(QColor("#2563eb"), 2))
            painter.drawLine(int(start_x), 0, int(start_x), self.height())
            painter.drawLine(int(end_x), 0, int(end_x), self.height())

        if self._samples:
            waveform_pen = QPen(QColor("#1f2937"), 1)
            painter.setPen(waveform_pen)
            mid = self.height() / 2
            points = []
            width = max(1, self.width() - 1)
            for index, sample in enumerate(self._samples):
                x = index * width / max(1, len(self._samples) - 1)
                height = max(1.0, sample * (self.height() * 0.46))
                points.append((x, mid - height, mid + height))
            for x, top, bottom in points:
                painter.drawLine(int(x), int(top), int(x), int(bottom))
        else:
            painter.setPen(QPen(QColor("#6b7280"), 1))
            painter.drawText(self.rect(), Qt.AlignCenter, "No waveform available")

        if self._duration_ms > 0:
            playhead_x = self._ms_to_x(self._position_ms)
            painter.setPen(QPen(QColor("#dc2626"), 2))
            painter.drawLine(int(playhead_x), 0, int(playhead_x), self.height())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or self._duration_ms <= 0:
            return

        x = max(0.0, min(float(event.position().x()), float(self.width())))
        handle_threshold = 8.0
        start_x = self._ms_to_x(self._clip_start_ms)
        end_x = self._ms_to_x(self._clip_end_ms)

        if self._clip_end_ms > self._clip_start_ms and abs(x - start_x) <= handle_threshold:
            self._drag_mode = "start"
            return
        if self._clip_end_ms > self._clip_start_ms and abs(x - end_x) <= handle_threshold:
            self._drag_mode = "end"
            return

        self.seek_requested.emit(self._x_to_ms(x))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode is None or self._duration_ms <= 0:
            return

        position_ms = self._x_to_ms(event.position().x())
        if self._drag_mode == "start":
            new_start = min(position_ms, max(0, self._clip_end_ms - 1))
            self.clip_range_changed.emit(new_start, self._clip_end_ms)
            return

        new_end = max(position_ms, self._clip_start_ms + 1)
        self.clip_range_changed.emit(self._clip_start_ms, new_end)

    def mouseReleaseEvent(self, _: QMouseEvent) -> None:
        self._drag_mode = None

    def _ms_to_x(self, position_ms: int) -> float:
        if self._duration_ms <= 0:
            return 0.0
        return (max(0, min(position_ms, self._duration_ms)) / self._duration_ms) * self.width()

    def _x_to_ms(self, x_pos: float) -> int:
        if self._duration_ms <= 0 or self.width() <= 0:
            return 0
        normalized = max(0.0, min(float(x_pos), float(self.width()))) / self.width()
        return int(normalized * self._duration_ms)
