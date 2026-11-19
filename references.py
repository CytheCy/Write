"""WordDesk lookups embedded in Write's reference side panels."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, QUrlQuery
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from reference_api import DICTIONARY_ENDPOINT, THESAURUS_ENDPOINT, MOBY_ENDPOINT, parse_response, parse_moby_response
from reference_widgets import ResultsView

SOURCES = {
    'Dictionary': (DICTIONARY_ENDPOINT, 'keys/dictionary_path',
                   'Search the Collegiate Dictionary for definitions, examples, and word history.'),
    'Thesaurus': (THESAURUS_ENDPOINT, 'keys/thesaurus_path',
                  'Search the Collegiate Thesaurus for meanings, synonyms, and antonyms.'),
    'Moby Thesaurus': (MOBY_ENDPOINT, None,
                       'Search the public-domain Moby Thesaurus for synonyms and related words. No API key is required.'),
}


class ReferencePanel(QWidget):
    def __init__(self, name, tools):
        super().__init__()
        self.setObjectName('referencePanel')
        self.setAccessibleName(name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Type a word…')
        self.search_input.setAccessibleName(f'{name} search')
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(0)
        self.search_input.returnPressed.connect(lambda: tools.search(self.search_input.text()))
        row.addWidget(self.search_input, 1)
        self.search_button = QPushButton('Search')
        self.search_button.clicked.connect(lambda: tools.search(self.search_input.text()))
        row.addWidget(self.search_button)
        layout.addLayout(row)
        if SOURCES[name][1]:
            settings_button = QPushButton('API key files…')
            settings_button.clicked.connect(tools.show_settings)
            layout.addWidget(settings_button)
        self.view = ResultsView('Ready for a word', SOURCES[name][2])
        self.view.word_requested.connect(tools.handle_word_request)
        layout.addWidget(self.view, 1)


class KeyPathRow(QWidget):
    def __init__(self, name, setting_key, settings):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(f'Merriam-Webster Collegiate {name} key file'))
        row = QHBoxLayout()
        self.path = QLineEdit(str(settings.value(setting_key, '')))
        self.path.setAccessibleName(f'{name} API key file')
        self.path.setPlaceholderText('Choose a .txt key file…')
        self.path.setReadOnly(True)
        row.addWidget(self.path, 1)
        choose = QPushButton('Choose file…')
        row.addWidget(choose)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.update_status()

        def choose_file():
            current = self.path.text()
            start = str(Path(current).parent if current else Path.home())
            selected, _ = QFileDialog.getOpenFileName(
                self, 'Choose API key file', start, 'Text files (*.txt);;All files (*)')
            if selected:
                self.path.setText(selected)
                settings.setValue(setting_key, selected)
                self.update_status()
        choose.clicked.connect(choose_file)

    def update_status(self):
        value = self.path.text()
        self.status.setText('No file selected' if not value else (
            'File found • the key will be read when you search' if Path(value).is_file()
            else 'File not found • choose a new location'))


class ReferenceTools(QObject):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings
        self.network = QNetworkAccessManager(self)
        self.pending = {}
        self.generation = 0
        self.panels = {name: ReferencePanel(name, self) for name in SOURCES}

    def show_settings(self):
        dialog = QDialog(self.parent())
        dialog.setWindowTitle('Reference API key files')
        dialog.resize(560, 280)
        layout = QVBoxLayout(dialog)
        helper = QLabel('Choose the text file containing each API key. Only file locations are saved. '
                        'Keys are read when searching and sent to Merriam-Webster over HTTPS.')
        helper.setWordWrap(True)
        layout.addWidget(helper)
        for name, (_, key, _) in SOURCES.items():
            if key:
                layout.addWidget(KeyPathRow(name, key, self.settings))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        dialog.deleteLater()

    def handle_word_request(self, word):
        if word == '__settings__':
            self.show_settings()
        else:
            self.search(word)

    def _read_key(self, name, setting_key, view):
        path = str(self.settings.value(setting_key, ''))
        if not path:
            view.show_error(f'{name} key is not set', 'Choose its .txt file in Settings, then search again.', True)
            return None
        try:
            key = Path(path).read_text(encoding='utf-8-sig').strip()
        except (OSError, UnicodeError):
            view.show_error(f'Could not read the {name.lower()} key',
                            'Choose a readable UTF-8 text file in Settings, then search again.', True)
            return None
        if not key:
            view.show_error(f'{name} key file is empty', 'Add the API key to the selected file, then search again.', True)
            return None
        return key

    def cancel(self):
        self.generation += 1
        for reply in list(self.pending):
            reply.abort()

    def search(self, word):
        word = word.strip()
        if not word:
            return
        self.cancel()
        for name, (endpoint, setting_key, _) in SOURCES.items():
            panel = self.panels[name]
            panel.search_input.setText(word)
            key = self._read_key(name, setting_key, panel.view) if setting_key else None
            if setting_key and key is None:
                continue
            url = QUrl(endpoint if name == 'Moby Thesaurus' else
                       endpoint + QUrl.toPercentEncoding(word).data().decode('ascii'))
            query = QUrlQuery()
            if setting_key:
                query.addQueryItem('key', key)
            else:
                query.addQueryItem('Database', 'moby-thesaurus')
                query.addQueryItem('Form', 'Dict2')
                query.addQueryItem('Query', word)
            url.setQuery(query)
            request = QNetworkRequest(url)
            request.setTransferTimeout(15_000)
            request.setRawHeader(b'Accept', b'text/html' if name == 'Moby Thesaurus' else b'application/json')
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, 'Write/1.0')
            panel.view.show_loading(word, 'Moby Thesaurus' if name == 'Moby Thesaurus' else 'Merriam-Webster')
            reply = self.network.get(request)
            self.pending[reply] = (self.generation, name, word)
            reply.finished.connect(lambda current=reply: self.request_finished(current))

    def request_finished(self, reply):
        context = self.pending.pop(reply, None)
        try:
            if context is None or context[0] != self.generation:
                return
            _, name, word = context
            view = self.panels[name].view
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NetworkError.NoError:
                if status in (401, 403) and SOURCES[name][1]:
                    view.show_error('API key was rejected', 'Check that the selected file contains the key for this API.', True)
                elif status == 429:
                    view.show_error('Request limit reached', 'The service has declined more requests for now.')
                else:
                    view.show_error('Could not complete the lookup', 'Check your connection and try again.')
                return
            try:
                text = bytes(reply.readAll()).decode('utf-8')
                entries, suggestions = (parse_moby_response(text, word) if name == 'Moby Thesaurus'
                                        else parse_response(json.loads(text)))
            except (UnicodeError, ValueError, TypeError, AttributeError):
                view.show_error('Could not read the response', 'The service returned an unexpected response. Try again.')
                return
            if entries:
                view.show_entries(entries, thesaurus=name != 'Dictionary',
                                  word_limit=None if name == 'Moby Thesaurus' else 12,
                                  word_label='RELATED WORDS' if name == 'Moby Thesaurus' else 'SYNONYMS')
            elif suggestions:
                view.show_suggestions(word, suggestions)
            else:
                view.show_error('No results', f'{name} returned no entries for “{word}”.')
        finally:
            reply.deleteLater()
