from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout, QWidget

from looped.domain.models import Track


class EditTrackDialog(QDialog):
    def __init__(self, track: Track, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.track = track

        self.setWindowTitle("Edit Track Info")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_input = QLineEdit(track.title)
        self.artist_input = QLineEdit(track.artist)
        self.album_input = QLineEdit(track.album)

        form.addRow("Title", self.title_input)
        form.addRow("Artist", self.artist_input)
        form.addRow("Album", self.album_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return (
            self.title_input.text(),
            self.artist_input.text(),
            self.album_input.text(),
        )
