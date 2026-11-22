"""Portable Markdown tree colors and a palette made from native Qt widgets."""
from functools import lru_cache
from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileSystemModel, QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget,
)


COLOR_HEADER = re.compile(r'\A<!-- write-project-color: (#[0-9a-fA-F]{6}) -->(?:\r\n|\r|\n|$)')
PALETTE = (
    ('Red', '#e05252'), ('Orange', '#e08735'), ('Amber', '#c99a26'),
    ('Green', '#48a868'), ('Teal', '#329e96'), ('Blue', '#528fdf'),
    ('Indigo', '#7b79dc'), ('Purple', '#ae6acc'), ('Pink', '#d46e9c'),
    ('Brown', '#aa8060'), ('Gray', '#9299a3'), ('Silver', '#c4c9d1'),
)


def split_project_color(source):
    """Only recognize our own leading comment, never examples in the body."""
    match = COLOR_HEADER.match(source)
    return (source[match.end():], match[0]) if match else (source, '')


def color_header(color):
    if color is None:
        return ''
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('Expected a six-digit hex color')
    return f'<!-- write-project-color: {color.lower()} -->\n'


def header_color(header):
    match = COLOR_HEADER.match(header)
    return match[1].lower() if match else None


@lru_cache(maxsize=2048)
def _read_color(path, signature):
    try:
        with open(path, 'rb') as source:
            # The complete header is ASCII; never scan a large note to paint a row.
            header = source.read(96).decode('utf-8-sig', errors='replace')
        return header_color(header)
    except OSError:
        return None


class ProjectFileSystemModel(QFileSystemModel):
    def file_color(self, index):
        path = Path(self.filePath(index))
        if path.suffix.lower() not in {'.md', '.markdown'} or self.isDir(index):
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        return _read_color(str(path), (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))

    def refresh_color(self, path):
        index = self.index(str(path))
        if index.isValid():
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.ForegroundRole,
                                                 Qt.ItemDataRole.DecorationRole])


class ProjectColorPopup(QWidget):
    colorSelected = Signal(object)

    def __init__(self, filename, current_color, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName('projectColorPopup')
        self.setWindowTitle('File color')
        self.setAccessibleName(f'Color for {filename}')
        layout = QVBoxLayout(self)
        title = QLabel(filename)
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)
        layout.addWidget(QLabel('Icon and filename color'))
        grid = QGridLayout()
        grid.setSpacing(5)
        self.swatches = []
        for number, (name, color) in enumerate(PALETTE):
            button = QToolButton(self)
            button.setFixedSize(32, 32)
            button.setCheckable(True)
            button.setChecked(color == current_color)
            button.setAccessibleName(name)
            button.setToolTip(f'{name} ({color})')
            ink = '#ffffff' if QColor(color).lightnessF() < 0.6 else '#202020'
            button.setText('✓' if button.isChecked() else '')
            button.setStyleSheet(
                f'QToolButton {{ background: {color}; color: {ink}; padding: 0; '
                'border: 2px solid transparent; border-radius: 4px; }'
                f'QToolButton:hover, QToolButton:focus, QToolButton:checked {{ border-color: {ink}; }}')
            button.clicked.connect(lambda _checked=False, value=color: self.choose(value))
            grid.addWidget(button, number // 6, number % 6)
            self.swatches.append(button)
        layout.addLayout(grid)
        self.default_button = QToolButton(self)
        self.default_button.setText('Default color')
        self.default_button.clicked.connect(lambda: self.choose(None))
        layout.addWidget(self.default_button)

    def choose(self, color):
        self.close()
        self.colorSelected.emit(color)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
