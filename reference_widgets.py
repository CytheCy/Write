from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from reference_api import Entry


class PlainLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)


class WordGrid(QWidget):
    """Reflow chips as the reference splitter changes width."""
    def __init__(self, words, callback):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.buttons = []
        self.columns = 0
        for word in words:
            button = WordButton(word)
            button.clicked.connect(lambda checked=False, value=word: callback(value))
            self.buttons.append(button)
        self.reflow()

    def reflow(self):
        preferred = max((b.sizeHint().width() for b in self.buttons), default=80)
        columns = max(1, min(4, (self.width() + 6) // (preferred + 6)))
        if columns == self.columns:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 0)
        self.columns = columns
        for index, button in enumerate(self.buttons):
            self.grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()


class WordButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("class", "wordChip")
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ResultsView(QScrollArea):
    word_requested = Signal(str)

    def __init__(self, empty_title: str, empty_body: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.empty_title = empty_title
        self.empty_body = empty_body
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 8, 0, 12)
        self._layout.setSpacing(12)
        self._layout.addStretch()
        self.setWidget(self._content)
        self.show_empty()

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

    def _message(self, title: str, body: str, action: str = "") -> None:
        self._clear()
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(7)
        title_label = PlainLabel(title)
        title_label.setWordWrap(True)
        title_label.setProperty("class", "emptyTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_label = PlainLabel(body)
        body_label.setProperty("class", "muted")
        body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        if action:
            button = QPushButton(action)
            button.setProperty("class", "secondary")
            button.setFixedWidth(150)
            button.clicked.connect(lambda: self.word_requested.emit("__settings__"))
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(button)
            row.addStretch()
            layout.addSpacing(8)
            layout.addLayout(row)
        layout.addStretch()
        self._layout.addWidget(holder)

    def show_empty(self) -> None:
        self._message(self.empty_title, self.empty_body)

    def show_loading(self, word: str, service: str = "Merriam-Webster") -> None:
        self._message(f"Looking up “{word}”", f"Contacting {service}…")

    def show_error(self, title: str, detail: str, settings_action: bool = False) -> None:
        self._message(title, detail, "Open settings" if settings_action else "")

    def show_suggestions(self, word: str, suggestions: list[str]) -> None:
        self._clear()
        label = PlainLabel("NO EXACT MATCH")
        label.setProperty("class", "sectionLabel")
        self._layout.addWidget(label)
        title = PlainLabel(f"Suggestions for “{word}”")
        title.setWordWrap(True)
        title.setProperty("class", "resultHeadword")
        self._layout.addWidget(title)
        helper = PlainLabel("Select a suggestion to search again.")
        helper.setWordWrap(True)
        helper.setProperty("class", "muted")
        self._layout.addWidget(helper)
        self._layout.addSpacing(6)
        for suggestion in suggestions:
            button = QPushButton(suggestion)
            button.setProperty("class", "suggestion")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=suggestion: self.word_requested.emit(value))
            self._layout.addWidget(button)
        self._layout.addStretch()

    def _word_row(self, label_text: str, words: list[str], limit: int | None = 12) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = PlainLabel(label_text)
        label.setProperty("class", "sectionLabel")
        layout.addWidget(label)
        visible_words = words if limit is None else words[:limit]
        layout.addWidget(WordGrid(visible_words, self.word_requested.emit))
        return block

    def show_entries(
        self,
        entries: list[Entry],
        thesaurus: bool = False,
        word_limit: int | None = 12,
        word_label: str = "SYNONYMS",
    ) -> None:
        self._clear()
        for entry_index, entry in enumerate(entries):
            card = QFrame()
            card.setProperty("class", "resultCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 12, 10, 12)
            card_layout.setSpacing(9)

            heading = QVBoxLayout()
            headword = PlainLabel(entry.headword)
            headword.setWordWrap(True)
            headword.setProperty("class", "resultHeadword")
            heading.addWidget(headword)
            if entry.functional_label:
                part = PlainLabel(entry.functional_label.upper())
                part.setWordWrap(True)
                part.setProperty("class", "partOfSpeech")
                heading.addWidget(part)
            if entry.pronunciation:
                pronunciation = PlainLabel(entry.pronunciation)
                pronunciation.setWordWrap(True)
                pronunciation.setProperty("class", "pronunciation")
                heading.addWidget(pronunciation)
            card_layout.addLayout(heading)

            if entry.senses:
                section = PlainLabel("MEANINGS" if thesaurus else "DEFINITIONS")
                section.setProperty("class", "sectionLabel")
                card_layout.addWidget(section)
                for index, sense in enumerate(entry.senses, 1):
                    sense_row = QHBoxLayout()
                    sense_row.setSpacing(10)
                    number = PlainLabel(sense.number or str(index))
                    number.setProperty("class", "senseNumber")
                    number.setFixedWidth(28)
                    number.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
                    sense_row.addWidget(number)
                    content = QWidget()
                    content_layout = QVBoxLayout(content)
                    content_layout.setContentsMargins(0, 0, 0, 0)
                    content_layout.setSpacing(5)
                    if sense.definition:
                        definition = PlainLabel(sense.definition)
                        definition.setWordWrap(True)
                        definition.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                        content_layout.addWidget(definition)
                    for example_text in sense.examples[:2]:
                        example = PlainLabel(example_text)
                        example.setProperty("class", "example")
                        example.setWordWrap(True)
                        content_layout.addWidget(example)
                    if sense.synonyms:
                        content_layout.addWidget(self._word_row("SYNONYMS", sense.synonyms, word_limit))
                    if sense.antonyms:
                        content_layout.addWidget(self._word_row("ANTONYMS", sense.antonyms, word_limit))
                    sense_row.addWidget(content, 1)
                    card_layout.addLayout(sense_row)
            elif not (entry.synonyms or entry.antonyms):
                unavailable = PlainLabel("No displayable definitions were included for this entry.")
                unavailable.setWordWrap(True)
                unavailable.setProperty("class", "muted")
                card_layout.addWidget(unavailable)

            if entry.synonyms:
                card_layout.addWidget(self._word_row(word_label, entry.synonyms, word_limit))
            if entry.antonyms:
                card_layout.addWidget(self._word_row("ANTONYMS", entry.antonyms, word_limit))
            if entry.etymology and not thesaurus:
                et_label = PlainLabel("WORD HISTORY")
                et_label.setProperty("class", "sectionLabel")
                card_layout.addWidget(et_label)
                et = PlainLabel(entry.etymology)
                et.setProperty("class", "muted")
                et.setWordWrap(True)
                card_layout.addWidget(et)

            self._layout.addWidget(card)
            if entry_index >= 7:
                break
        self._layout.addStretch()
