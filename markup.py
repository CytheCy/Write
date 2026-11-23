"""Project-local watch/replacement categories and their editor presentation."""
from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import QEvent, QFileSystemWatcher, QObject, QSaveFile, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget, QWidgetAction,
)
from project_colors import PALETTE

DEFAULT_COLOR = PALETTE[2][1]
COLOR_LINE = re.compile(r'^#\s*color:\s*(#[0-9a-fA-F]{6})\s*$', re.I)


@dataclass
class Category:
    path: Path
    color: str
    rules: list

    @property
    def name(self):
        return self.path.stem


def read_category(path):
    color, rules = DEFAULT_COLOR, []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        match = COLOR_LINE.fullmatch(line)
        if match:
            color = match[1].lower()
        elif '|' in line:
            watch, replacement = line.split('|', 1)
            if watch:
                rules.append((watch, replacement))
    return Category(path, color, rules)


def write_category(path, color, rules):
    """Commit complete category files so a failed save leaves the old file intact."""
    payload = (f'# color: {color}\n' + ''.join(f'{a}|{b}\n' for a, b in rules)).encode('utf-8')
    output = QSaveFile(str(path))
    if not output.open(QSaveFile.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if output.write(payload) != len(payload) or not output.commit():
        raise OSError(output.errorString())


class CategoryMatcher:
    """Compile project rules once and reuse them for individual paragraphs."""

    def __init__(self, categories):
        self.values = values = {}
        for category in categories:
            for watch, replacement in category.rules:
                values.setdefault(watch, (replacement, category.color))
        # Explicit rules take priority over automatic first-letter variants.
        for watch, value in list(values.items()):
            for initial in (watch[0].lower(), watch[0].upper()):
                values.setdefault(initial + watch[1:], value)
        # Prefer a phrase over a shorter watch starting at the same position.
        alternatives = [
            (r'(?<!\w)' if watch[0].isalnum() or watch[0] == '_' else '')
            + re.escape(watch)
            + (r'(?!\w)' if watch[-1].isalnum() or watch[-1] == '_' else '')
            for watch in sorted(values, key=len, reverse=True)
        ]
        self.pattern = re.compile('|'.join(alternatives)) if alternatives else None

    def matches(self, text):
        if self.pattern is None:
            return
        for match in self.pattern.finditer(text):
            replacement, color = self.values[match[0]]
            if match[0][0].isupper():
                replacement = replacement[:1].upper() + replacement[1:]
            yield match.start(), match.end(), replacement, color


def category_matches(text, categories):
    """Match literal words/phrases, allowing either case of the first letter."""
    return CategoryMatcher(categories).matches(text)


class CategoryDialog(QDialog):
    def __init__(self, directory, category=None, parent=None):
        super().__init__(parent)
        self.directory, self.category = directory, category
        self.setWindowTitle('Edit Markup Category' if category else 'Add New Category')
        self.resize(540, 430)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(category.name if category else '')
        self.name_input.setObjectName('markupCategoryName')
        form.addRow('Name', self.name_input)
        layout.addLayout(form)
        layout.addWidget(QLabel('Text color'))
        grid = QGridLayout()
        self.colors = QButtonGroup(self)
        self.color = category.color if category else DEFAULT_COLOR
        self.swatches = []
        for number, (name, color) in enumerate(PALETTE):
            button = QToolButton()
            button.setFixedSize(32, 32)
            button.setCheckable(True)
            button.setChecked(color == self.color)
            button.setAccessibleName(name)
            button.setToolTip(f'{name} ({color})')
            ink = '#ffffff' if QColor(color).lightnessF() < 0.6 else '#202020'
            button.setStyleSheet(
                f'QToolButton {{ background: {color}; border: 2px solid transparent; border-radius: 4px; }}'
                f'QToolButton:hover, QToolButton:focus, QToolButton:checked {{ border-color: {ink}; }}')
            button.clicked.connect(lambda checked=False, value=color: setattr(self, 'color', value))
            self.colors.addButton(button)
            self.swatches.append(button)
            grid.addWidget(button, number // 6, number % 6)
        layout.addLayout(grid)
        hint = QLabel('First-letter capitalization is automatic. '
                      'Ctrl+left-click colored text to replace it.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.rules = QTableWidget(0, 2)
        self.rules.setObjectName('markupRules')
        self.rules.setHorizontalHeaderLabels(['Watch for', 'Change to'])
        self.rules.horizontalHeader().setStretchLastSection(True)
        self.rules.setColumnWidth(0, 240)
        layout.addWidget(self.rules)
        for watch, replacement in category.rules if category else [('', '')]:
            self.add_rule(watch, replacement)
        buttons = QHBoxLayout()
        add = QPushButton('Add word or phrase')
        add.clicked.connect(lambda: self.add_rule())
        remove = QPushButton('Remove selected row')
        remove.clicked.connect(self.remove_rows)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        layout.addLayout(buttons)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.save)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)
        self.saved_path = None

    def add_rule(self, watch='', replacement=''):
        row = self.rules.rowCount()
        self.rules.insertRow(row)
        for column, value in enumerate((watch, replacement)):
            self.rules.setItem(row, column, QTableWidgetItem(value))

    def remove_rows(self):
        for row in sorted({index.row() for index in self.rules.selectedIndexes()}, reverse=True):
            self.rules.removeRow(row)

    def save(self):
        name = self.name_input.text().strip()
        if not name or name in ('.', '..') or any(c in name for c in '/\\\x00\r\n') or name.startswith('.'):
            self.error.setText('Enter a category name without path separators or a leading dot.')
            return
        path = self.directory / f'{name}.txt'
        if path.exists() and (self.category is None or path != self.category.path):
            self.error.setText('A category with that name already exists.')
            return
        rules = []
        for row in range(self.rules.rowCount()):
            values = [self.rules.item(row, col).text() if self.rules.item(row, col) else '' for col in range(2)]
            if not any(values):
                continue
            watch, replacement = values
            if not watch or '|' in watch or any(c in watch + replacement for c in '\r\n\x00'):
                self.error.setText('Each row needs a watch. Watches cannot contain |; entries must be single lines.')
                return
            rules.append((watch, replacement))
        try:
            write_category(path, self.color, rules)
            if self.category and path != self.category.path:
                try:
                    self.category.path.unlink()
                except OSError:
                    path.unlink()
                    raise
        except OSError as error:
            self.error.setText(f'Could not save category: {error}')
            return
        self.saved_path = path
        self.accept()


class MarkupController(QObject):
    def __init__(self, window, button):
        super().__init__(window)
        self.window, self.editor, self.button = window, window.editor, button
        self.viewport = self.editor.viewport()
        self.editor.destroyed.connect(self.shutdown)
        self.categories = []
        self.matcher = CategoryMatcher([])
        self.colors = {}
        self._rule_signature = ()
        self.editor.markup_controller = self
        self.menu = QMenu(window)
        self.menu.setObjectName('markupPopup')
        self.menu.installEventFilter(self)
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(250)
        self.hover_timer.timeout.connect(self.dismiss_after_hover)
        self.dialog = None
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.schedule_reload)
        self.watcher.fileChanged.connect(self.schedule_reload)
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(100)
        self.reload_timer.timeout.connect(self.reload)
        button.installEventFilter(self)
        button.clicked.connect(self.show_popup)
        self.viewport.installEventFilter(self)
        self.set_root(window.project_tree_path)

    def shutdown(self):
        self.hover_timer.stop()
        self.reload_timer.stop()
        self.watcher.blockSignals(True)

    def set_root(self, root):
        self.menu.close()
        if self.dialog:
            self.dialog.reject()
        self.directory = Path(root) / '.app' / 'markup'
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(self.window, 'Markup folder could not be created', str(error))
        self.reload()

    def enabled_key(self, name):
        return f'markup/{self.directory.parent.parent.as_uri()}/{name}'

    def enabled(self, category):
        return self.window.settings.value(self.enabled_key(category.name), True, type=bool)

    def schedule_reload(self, *_):
        self.reload_timer.start()

    def reload(self):
        self.categories = []
        self.errors = []
        try:
            paths = sorted(self.directory.glob('*.txt'), key=lambda path: path.name.casefold())
            for path in paths:
                if path.name.startswith('.'):
                    continue
                try:
                    self.categories.append(read_category(path))
                except (OSError, UnicodeError) as error:
                    self.errors.append(f'{path.name}: {error}')
        except OSError as error:
            self.errors.append(str(error))
        watched = self.watcher.files() + self.watcher.directories()
        if watched:
            self.watcher.removePaths(watched)
        paths = [str(c.path) for c in self.categories]
        if self.directory.is_dir():
            paths.append(str(self.directory))
        if paths:
            self.watcher.addPaths(paths)
        self.refresh()

    def show_popup(self):
        if self.menu.isVisible() or self.dialog:
            return
        self.reload()
        self.menu.clear()
        if not self.categories:
            self.menu.addAction('No markup categories yet').setEnabled(False)
        for category in self.categories:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 3, 8, 3)
            check = QCheckBox(category.name)
            check.setChecked(self.enabled(category))
            check.toggled.connect(lambda enabled, c=category: self.toggle(c, enabled))
            layout.addWidget(check, 1)
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f'background: {category.color}; border-radius: 3px;')
            layout.addWidget(swatch)
            edit = QToolButton()
            icon = QPixmap(str(Path(__file__).parent / 'boxicons' / 'bx-edit.svg'))
            painter = QPainter(icon)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(icon.rect(), QColor(self.window.theme['text']))
            painter.end()
            edit.setIcon(QIcon(icon))
            edit.setAccessibleName(f'Edit {category.name}')
            edit.setToolTip(f'Edit {category.name}')
            edit.clicked.connect(lambda checked=False, c=category: self.edit(c))
            layout.addWidget(edit)
            action = QWidgetAction(self.menu)
            action.setDefaultWidget(row)
            self.menu.addAction(action)
        for error in self.errors:
            self.menu.addAction(error).setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction('Add New Category', lambda: self.edit())
        self.menu.popup(self.button.mapToGlobal(self.button.rect().topRight()))

    def dismiss_after_hover(self):
        point = QCursor.pos()
        if not any(widget.rect().contains(widget.mapFromGlobal(point))
                   for widget in (self.button, self.menu)):
            self.menu.close()

    def toggle(self, category, enabled):
        self.window.settings.setValue(self.enabled_key(category.name), enabled)
        self.refresh()

    def edit(self, category=None):
        self.menu.close()
        self.dialog = CategoryDialog(self.directory, category, self.window)
        self.dialog.finished.connect(self.edit_finished)
        self.dialog.open()

    def edit_finished(self, result):
        dialog = self.dialog
        if result == QDialog.DialogCode.Accepted and dialog.category:
            self.window.settings.setValue(self.enabled_key(dialog.saved_path.stem), self.enabled(dialog.category))
        self.dialog = None
        dialog.deleteLater()
        self.reload()

    def refresh(self):
        """Rebuild and repaint only when the enabled rules actually change."""
        active = [c for c in self.categories if self.enabled(c) and c.rules]
        signature = tuple((c.color, tuple(c.rules)) for c in active)
        if signature == self._rule_signature:
            return
        self._rule_signature = signature
        self.matcher = CategoryMatcher(active)
        self.colors = {c.color: QColor(c.color) for c in active}
        highlighter = getattr(self.editor, 'highlighter', None)
        if highlighter is not None:
            document = self.editor.document()
            was_modified = document.isModified()
            highlighter.rehighlight()
            document.setModified(was_modified)

    def highlight_block(self, highlighter, text):
        """Merge foregrounds into syntax formats without retaining live cursors."""
        if self.matcher.pattern is None:
            return
        offsets = None
        if not highlighter.block_is_bmp:
            offsets, position = [0], 0
            for char in text:
                position += 2 if ord(char) > 0xffff else 1
                offsets.append(position)
        for start, end, _, color in self.matcher.matches(text):
            if offsets is not None:
                start, end = offsets[start], offsets[end]
            while start < end:
                style = highlighter.format(start)
                limit = start + 1
                while limit < end and highlighter.format(limit) == style:
                    limit += 1
                # Keep collapsed Markdown markers and table source invisible.
                if style.foreground().color().alpha():
                    style.setForeground(self.colors[color])
                    highlighter.setFormat(start, limit - start, style)
                start = limit

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.button and event.type() == QEvent.Type.Enter:
            self.show_popup()
        if watched is self.button or watched is self.menu:
            if event.type() in (QEvent.Type.Leave, QEvent.Type.MouseMove):
                self.hover_timer.start()
        elif (watched is self.viewport and event.type() == QEvent.Type.MouseButtonPress
              and event.button() == Qt.MouseButton.LeftButton
              and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            point = event.position().toPoint()
            hit = self.editor.cursorForPosition(point)
            rect = self.editor.cursorRect(hit)
            if not rect.top() <= point.y() <= rect.bottom():
                return False
            if point.x() < rect.left():
                hit.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
            start_rect = self.editor.cursorRect(hit)
            character = QTextCursor(hit)
            character.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            end_rect = self.editor.cursorRect(character)
            right = (end_rect.left() if end_rect.top() == start_rect.top() else
                     start_rect.left() + self.editor.fontMetrics().horizontalAdvance(character.selectedText()))
            if not start_rect.left() <= point.x() < right:
                return False
            block = hit.block()
            text = block.text()
            position = hit.positionInBlock()
            for start, end, replacement, _ in self.matcher.matches(text):
                start = len(text[:start].encode('utf-16-le')) // 2
                end = len(text[:end].encode('utf-16-le')) // 2
                if start <= position < end:
                    cursor = QTextCursor(block)
                    cursor.setPosition(block.position() + start)
                    cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
                    cursor.beginEditBlock()
                    cursor.insertText(replacement)
                    cursor.endEditBlock()
                    self.editor.setTextCursor(cursor)
                    event.accept()
                    return True
        return super().eventFilter(watched, event)
