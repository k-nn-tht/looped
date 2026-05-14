from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QTableWidget


class TrackTableWidget(QTableWidget):
    paths_dropped = Signal(list)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self._default_stylesheet = ""
        self._drag_stylesheet = "QTableWidget { border: 2px dashed #2563eb; }"

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        paths = self._extract_paths(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self._set_drag_active(True)

    def dragMoveEvent(self, event) -> None:
        paths = self._extract_paths(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._extract_paths(event)
        self._set_drag_active(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.paths_dropped.emit(paths)

    def _set_drag_active(self, active: bool) -> None:
        self.setStyleSheet(self._drag_stylesheet if active else self._default_stylesheet)

    @staticmethod
    def _extract_paths(event) -> list[str]:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return []

        paths: list[str] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.exists():
                paths.append(str(path))
        return paths
