"""Asynchronous literal project search and grouped, highlighted results."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import os
import re
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QTextDocument
from PySide6.QtWidgets import (QComboBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
                               QStyledItemDelegate, QStyle, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)


@dataclass(frozen=True)
class Match:
    path: Path
    start: int
    end: int
    excerpt: str
    highlight_start: int
    highlight_end: int


def search_project(root, query, cancelled, snapshots=None, limit=2000):
    """Search UTF-8 text recursively, skipping binary files and symlinks.

    Snapshot sources let open documents include edits that are not saved yet.
    The result cap bounds memory use and rendering for very broad searches.
    """
    matches, errors = [], []
    if not query:
        return matches, False, errors
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    snapshots = snapshots or {}
    def walk_error(error):
        errors.append(str(error))
    for directory, folders, files in os.walk(root, onerror=walk_error):
        folders[:] = [name for name in folders if name not in ('.git', '.app')
                      and not Path(directory, name).is_symlink()]
        for name in files:
            if cancelled.is_set():
                return [], False, []
            path = Path(directory, name)
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path in snapshots:
                    source = snapshots[path]
                else:
                    # Read in chunks so cancellation also interrupts large files.
                    chunks = []
                    with path.open('rb') as stream:
                        while chunk := stream.read(65536):
                            if cancelled.is_set():
                                return [], False, []
                            if b'\0' in chunk:
                                break
                            chunks.append(chunk)
                        else:
                            chunk = b''
                    if chunk:
                        continue
                    source = b''.join(chunks).decode('utf-8-sig')
                source = source.replace('\r\n', '\n').replace('\r', '\n')
            except UnicodeError:
                continue
            except OSError as error:
                errors.append(str(error))
                continue
            for match in pattern.finditer(source):
                if cancelled.is_set():
                    return [], False, []
                if len(matches) == limit:
                    return matches, True, errors
                start, end = match.span()
                left = max(source.rfind('\n', 0, start) + 1, start - 65)
                newline = source.find('\n', end)
                right = min(len(source) if newline < 0 else newline, end + 100)
                prefix = '…' if left and source[left - 1] != '\n' else ''
                suffix = '…' if right < len(source) and source[right] != '\n' else ''
                excerpt = prefix + source[left:right] + suffix
                matches.append(Match(path, start, end, excerpt,
                                     len(prefix) + start - left, len(prefix) + end - left))
    return matches, False, errors


class SearchSignals(QObject):
    finished = Signal(int, object)


class SearchJob(QRunnable):
    def __init__(self, generation, root, query, snapshots):
        super().__init__()
        self.generation, self.root, self.query = generation, root, query
        self.snapshots = snapshots
        self.cancelled = Event()
        self.signals = SearchSignals()

    def run(self):
        result = search_project(self.root, self.query, self.cancelled, self.snapshots)
        self.signals.finished.emit(self.generation, result)


class SnippetDelegate(QStyledItemDelegate):
    def document(self, option, index):
        match = index.data(Qt.ItemDataRole.UserRole)
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setDocumentMargin(7)
        theme = self.parent().window().theme
        doc.setDefaultStyleSheet(f"body {{ color: {theme['text']}; }}")
        text = match.excerpt
        doc.setHtml('<body>' + escape(text[:match.highlight_start]) +
                    f'<span style="background-color:{theme["selection"]}; '
                    f'color:{theme["selection_text"]}">' +
                    escape(text[match.highlight_start:match.highlight_end]) + '</span>' +
                    escape(text[match.highlight_end:]) + '</body>')
        doc.setTextWidth(max(70, self.parent().viewport().width() - 30))
        return doc

    def sizeHint(self, option, index):
        if index.parent().isValid() and index.column() == 0:
            doc = self.document(option, index)
            return QSize(80, int(doc.size().height()) + 7)
        size = super().sizeHint(option, index)
        return QSize(80, max(34, size.height()))

    def paint(self, painter, option, index):
        if not index.parent().isValid() or index.column() != 0:
            return super().paint(painter, option, index)
        theme = self.parent().window().theme
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setBrush(QColor(theme['hover'] if selected else theme['panel']))
        painter.setPen(QColor(theme['border']))
        painter.drawRoundedRect(option.rect.adjusted(1, 1, -2, -4), 5, 5)
        painter.setClipRect(option.rect)
        painter.translate(option.rect.topLeft())
        self.document(option, index).drawContents(painter)
        painter.restore()


class SearchResults(QTreeWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scheduleDelayedItemsLayout()


class ProjectSearchPanel(QWidget):
    match_requested = Signal(object)

    def __init__(self, root, snapshots, parent=None):
        super().__init__(parent)
        self.setObjectName('projectSearchPanel')
        self.root, self.snapshots = Path(root), snapshots
        self.generation = 0
        self.job = None
        self.matches = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 10)
        header = QHBoxLayout()
        header.addWidget(QLabel('Search project'), 1)
        layout.addLayout(header)
        self.root_label = QLabel()
        self.root_label.setTextFormat(Qt.TextFormat.PlainText)
        self.root_label.setWordWrap(True)
        layout.addWidget(self.root_label)
        self.input = QLineEdit()
        self.input.setAccessibleName('Search entire project')
        self.input.setPlaceholderText('Search project…')
        self.input.setClearButtonEnabled(True)
        layout.addWidget(self.input)
        summary = QHBoxLayout()
        self.count = QLabel('Enter text to search')
        self.count.setWordWrap(True)
        summary.addWidget(self.count, 1)
        self.sort = QComboBox()
        self.sort.addItems(['File name (A to Z)', 'File name (Z to A)'])
        self.sort.setAccessibleName('Sort search results')
        self.sort.setMinimumWidth(0)
        summary.addWidget(self.sort)
        layout.addLayout(summary)
        self.results = SearchResults()
        self.results.setObjectName('projectSearchResults')
        self.results.setAccessibleName('Project search results')
        self.results.setColumnCount(2)
        self.results.header().setStretchLastSection(False)
        self.results.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.results.setColumnWidth(1, 35)
        self.results.setHeaderHidden(True)
        self.results.setIndentation(16)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setItemDelegate(SnippetDelegate(self.results))
        self.results.itemClicked.connect(self.activate)
        self.results.itemActivated.connect(self.activate)
        layout.addWidget(self.results, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.search)
        self.input.textChanged.connect(self.schedule_search)
        self.input.returnPressed.connect(self.search)
        self.sort.currentIndexChanged.connect(self.render)
        self.set_root(root)

    def cancel(self):
        self.timer.stop()
        self.generation += 1
        if self.job:
            self.job.cancelled.set()
            self.job = None

    def set_root(self, root):
        self.root = Path(root)
        self.root_label.setText(self.root.name or str(self.root))
        self.root_label.setToolTip(str(self.root))
        self.schedule_search()

    def schedule_search(self):
        self.cancel()
        self.matches = []
        self.results.clear()
        self.count.setText('Searching…' if self.input.text() else 'Enter text to search')
        if self.input.text():
            self.timer.start()

    def search(self):
        self.cancel()
        if not self.input.text():
            return
        self.count.setText('Searching…')
        self.job = SearchJob(self.generation, self.root, self.input.text(), self.snapshots())
        self.job.signals.finished.connect(self.finished)
        QThreadPool.globalInstance().start(self.job)

    def finished(self, generation, result):
        if generation != self.generation:
            return
        self.job = None
        self.matches, limited, errors = result
        total = len(self.matches)
        self.count.setText(f'{total}{"+" if limited else ""} result{"s" if total != 1 else ""}' +
                           (' • Some files unavailable' if errors else ''))
        self.count.setToolTip(('Showing first 2000 results. Refine your search.\n' if limited else '') +
                              '\n'.join(errors[:10]))
        self.render()

    def render(self):
        self.results.clear()
        groups = {}
        for match in self.matches:
            groups.setdefault(match.path, []).append(match)
        for path in sorted(groups, key=lambda p: (p.name.casefold(), str(p).casefold()),
                           reverse=self.sort.currentIndex() == 1):
            matches = groups[path]
            group = QTreeWidgetItem([path.stem, str(len(matches))])
            group.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            group.setToolTip(0, str(path.relative_to(self.root)))
            self.results.addTopLevelItem(group)
            for match in matches:
                item = QTreeWidgetItem([match.excerpt])
                item.setData(0, Qt.ItemDataRole.UserRole, match)
                item.setToolTip(0, str(path.relative_to(self.root)))
                group.addChild(item)
                item.setFirstColumnSpanned(True)
            group.setExpanded(True)

    def activate(self, item, column):
        match = item.data(0, Qt.ItemDataRole.UserRole)
        if match:
            self.match_requested.emit(match)
