"""Saved AI requests and an asynchronous, cancellable writing panel."""
import base64
import json
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile
from xml.etree import ElementTree

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

DEFAULT_ENDPOINT = 'https://api.openai.com/v1/chat/completions'
ATTACHMENT_FILTER = ('Supporting files (*.txt *.md *.markdown *.csv *.json *.html *.xml '
                     '*.docx *.pdf *.png *.jpg *.jpeg *.webp);;All files (*)')
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def build_payload(model, prompt, selection, paths):
    """Keep instructions, target text, and supporting material distinct."""
    content = [{'type': 'text', 'text': 'Selected document text (the material to work on):\n' + selection}]
    total = 0
    for path in paths:
        path = Path(path)
        if path.stat().st_size > MAX_ATTACHMENT_BYTES - total:
            raise ValueError('Attachments must total no more than 20 MB.')
        data = path.read_bytes()
        total += len(data)
        if total > MAX_ATTACHMENT_BYTES:
            raise ValueError('Attachments must total no more than 20 MB.')
        suffix = path.suffix.lower()
        if suffix in ('.png', '.jpg', '.jpeg', '.webp', '.pdf'):
            mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp', '.pdf': 'application/pdf'}[suffix]
            encoded = f'data:{mime};base64,' + base64.b64encode(data).decode('ascii')
            if suffix == '.pdf':
                content.append({'type': 'file', 'file': {'filename': path.name, 'file_data': encoded}})
            else:
                content.append({'type': 'image_url', 'image_url': {'url': encoded}})
            continue
        if suffix == '.docx':
            with ZipFile(path) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > MAX_ATTACHMENT_BYTES:
                    raise ValueError(f'{path.name}: document is too large.')
                root = ElementTree.fromstring(archive.read(info))
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            text = '\n'.join(''.join(node.itertext()) for node in root.iter(ns + 'p'))
        else:
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise ValueError(f'{path.name}: use UTF-8 text, DOCX, PDF, or an image.') from None
            if '\x00' in text:
                raise ValueError(f'{path.name}: this file is not a supported text attachment.')
        content.append({'type': 'text', 'text': f'Supporting attachment: {path.name}\n{text}'})
    return {'model': model, 'messages': [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': content},
    ]}


def response_text(data):
    try:
        message = data['choices'][0]['message']
        text = message.get('content')
        if isinstance(text, list):
            text = '\n'.join(part.get('text', '') for part in text if part.get('type') == 'text')
        if not isinstance(text, str) or not text.strip():
            raise ValueError(message.get('refusal') or 'The AI returned no text.')
        return text
    except (KeyError, IndexError, TypeError):
        raise ValueError('The AI returned an unexpected response format.') from None


class RequestDialog(QDialog):
    def __init__(self, parent, name='', prompt=''):
        super().__init__(parent)
        self.setWindowTitle('AI request')
        self.resize(520, 400)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setAccessibleName('Request name')
        form.addRow('Name:', self.name)
        layout.addLayout(form)
        layout.addWidget(QLabel('Prompt'))
        self.prompt = QTextEdit()
        self.prompt.setAcceptRichText(False)
        self.prompt.setPlainText(prompt)
        self.prompt.setAccessibleName('Request prompt')
        self.prompt.setPlaceholderText('Describe what the AI should do to the selected text…')
        layout.addWidget(self.prompt)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.name.textChanged.connect(self.validate)
        self.prompt.textChanged.connect(self.validate)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.validate()

    def validate(self):
        self.save.setEnabled(bool(self.name.text().strip() and self.prompt.toPlainText().strip()))


class AIPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.settings = window.settings
        self.cursor = None
        self.selected_text = ''
        self.reply = None
        self.result_cursor = None
        self.result_selection = ''
        self.network = QNetworkAccessManager(self)
        self.network.setRedirectPolicy(QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.timed_out)
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel('AI requests'), 1)
        add = QPushButton('+')
        add.setAccessibleName('Add AI request')
        add.setToolTip('Add a request')
        add.clicked.connect(self.add_request)
        header.addWidget(add)
        close = QPushButton('×')
        close.setAccessibleName('Close AI panel')
        close.clicked.connect(window.close_left_panel)
        header.addWidget(close)
        layout.addLayout(header)
        self.requests = QListWidget()
        self.requests.setAccessibleName('AI requests — click to run')
        self.requests.setMaximumHeight(90)
        self.requests.itemClicked.connect(self.run_request)
        self.requests.itemActivated.connect(self.run_request)
        layout.addWidget(self.requests)
        edit = QPushButton('Edit request…')
        edit.clicked.connect(self.edit_request)
        layout.addWidget(edit)
        self.selection_label = QLabel('Select text in the document, then open AI.')
        self.selection_label.setWordWrap(True)
        layout.addWidget(self.selection_label)
        capture = QPushButton('Use current selection')
        capture.clicked.connect(self.capture_selection)
        layout.addWidget(capture)
        layout.addWidget(QLabel('Attachments · supporting content'))
        self.attachments = QListWidget()
        self.attachments.setAccessibleName('AI attachments')
        self.attachments.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.attachments.setMaximumHeight(75)
        layout.addWidget(self.attachments)
        row = QHBoxLayout()
        attach = QPushButton('Add files…')
        attach.clicked.connect(self.add_attachments)
        row.addWidget(attach)
        remove = QPushButton('Remove')
        remove.clicked.connect(self.remove_attachments)
        row.addWidget(remove)
        layout.addLayout(row)
        layout.addWidget(QLabel('Result'))
        self.output = QTextEdit()
        self.output.setAcceptRichText(False)
        self.output.setAccessibleName('AI result')
        self.output.setPlaceholderText('Click a request above to send the selection and attachments.')
        layout.addWidget(self.output, 1)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.cancel = QPushButton('Cancel request')
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_request)
        layout.addWidget(self.cancel)
        self.paste = QPushButton('Paste above selected')
        self.paste.setEnabled(False)
        self.paste.clicked.connect(self.paste_above)
        layout.addWidget(self.paste)
        self.output.textChanged.connect(self.update_paste)
        self.load_requests()

    def load_requests(self):
        try:
            saved = json.loads(self.settings.value('ai/requests', '[]', type=str))
        except (ValueError, TypeError):
            saved = []
        self.requests.clear()
        if not isinstance(saved, list):
            return
        for request in saved:
            if (isinstance(request, dict) and isinstance(request.get('name'), str)
                    and isinstance(request.get('prompt'), str)):
                self.insert_request(request['name'], request['prompt'])

    def insert_request(self, name, prompt):
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, prompt)
        item.setToolTip(prompt)
        self.requests.addItem(item)

    def save_requests(self):
        self.settings.setValue('ai/requests', json.dumps([
            {'name': self.requests.item(i).text(),
             'prompt': self.requests.item(i).data(Qt.ItemDataRole.UserRole)}
            for i in range(self.requests.count())]))
        self.settings.sync()

    def add_request(self):
        dialog = RequestDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.insert_request(dialog.name.text().strip(), dialog.prompt.toPlainText().strip())
            self.save_requests()

    def edit_request(self):
        item = self.requests.currentItem()
        if item is None:
            self.status.setText('Choose a request to edit.')
            return
        dialog = RequestDialog(self, item.text(), item.data(Qt.ItemDataRole.UserRole))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            item.setText(dialog.name.text().strip())
            item.setData(Qt.ItemDataRole.UserRole, dialog.prompt.toPlainText().strip())
            item.setToolTip(dialog.prompt.toPlainText().strip())
            self.save_requests()

    def capture_selection(self):
        if self.reply is not None:
            self.status.setText('Wait for this request or cancel it before changing the selection.')
            return
        self.cursor = QTextCursor(self.window.editor.textCursor())
        self.selected_text = self.cursor.selectedText()
        count = len(self.selected_text.replace('\u2029', '\n'))
        self.selection_label.setText(f'Selected text: {count:,} characters' if count else
                                     'Select text in the document, then click Use current selection.')

    def add_attachments(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add AI attachments', '', ATTACHMENT_FILTER)
        existing = {self.attachments.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.attachments.count())}
        for path in paths:
            if path not in existing:
                item = QListWidgetItem(Path(path).name())
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.attachments.addItem(item)
                existing.add(path)

    def remove_attachments(self):
        for item in self.attachments.selectedItems():
            self.attachments.takeItem(self.attachments.row(item))

    def valid_target(self, cursor, text):
        return (cursor is not None and isValid(cursor.document())
                and cursor.document() is self.window.editor.document()
                and cursor.hasSelection() and cursor.selectedText() == text)

    def run_request(self, item):
        if self.reply is not None:
            return
        if not self.valid_target(self.cursor, self.selected_text):
            self.status.setText('Select text in the document and click Use current selection.')
            return
        try:
            key_path = self.settings.value('ai/key_file', '', type=str)
            if not key_path:
                raise ValueError('Choose an API key file in Settings → AI.')
            key = Path(key_path).expanduser().read_text(encoding='utf-8-sig').strip()
            if not key or any(ch.isspace() for ch in key):
                raise ValueError('The API key file must contain only the API key.')
            model = self.settings.value('ai/model', '', type=str).strip()
            endpoint = self.settings.value('ai/endpoint', DEFAULT_ENDPOINT, type=str).strip()
            parsed = urlparse(endpoint)
            if not model:
                raise ValueError('Enter the AI model in Settings → AI.')
            if (not parsed.hostname or parsed.username or parsed.password or parsed.fragment
                    or parsed.scheme not in ('https', 'http')
                    or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
                raise ValueError('Use an HTTPS endpoint (HTTP is allowed for localhost).')
            payload = build_payload(model, item.data(Qt.ItemDataRole.UserRole),
                                    self.selected_text.replace('\u2029', '\n'),
                                    [self.attachments.item(i).data(Qt.ItemDataRole.UserRole)
                                     for i in range(self.attachments.count())])
        except Exception as error:
            self.status.setText(str(error))
            return
        self.result_cursor = None
        self.output.clear()
        self.pending_cursor = QTextCursor(self.cursor)
        self.pending_selection = self.selected_text
        request = QNetworkRequest(QUrl(endpoint))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, 'application/json')
        request.setRawHeader(b'Authorization', ('Bearer ' + key).encode('utf-8'))
        request.setTransferTimeout(120000)
        self.reply = self.network.post(request, QByteArray(json.dumps(payload).encode('utf-8')))
        self.reply.finished.connect(self.finished)
        self.requests.setEnabled(False)
        self.cancel.setEnabled(True)
        self.status.setText(f'Running {item.text()}…')
        self.timeout.start(120000)

    def finished(self):
        reply = self.reply
        if reply is None:
            return
        self.reply = None
        self.timeout.stop()
        self.requests.setEnabled(True)
        self.cancel.setEnabled(False)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                raise ValueError(f'AI request failed (HTTP {code}). Check Settings and try again.' if code
                                 else 'AI request failed. Check the connection and try again.')
            code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if code is None or not 200 <= int(code) < 300:
                raise ValueError('The endpoint did not return a successful response. Check Settings → AI.')
            text = response_text(json.loads(bytes(reply.readAll())))
            self.result_cursor = self.pending_cursor
            self.result_selection = self.pending_selection
            self.output.setPlainText(text)
            self.status.setText('Result ready. You can edit it before pasting.')
        except (ValueError, TypeError) as error:
            self.status.setText(str(error))
        finally:
            reply.deleteLater()

    def update_paste(self):
        self.paste.setEnabled(self.result_cursor is not None and bool(self.output.toPlainText().strip()))

    def paste_above(self):
        if not self.valid_target(self.result_cursor, self.result_selection):
            self.status.setText('The original selection changed or its document is not active. Return to it or run a new request.')
            return
        text = self.output.toPlainText()
        if not text.strip():
            return
        cursor = QTextCursor(self.result_cursor)
        cursor.setPosition(cursor.selectionStart())
        cursor.beginEditBlock()
        cursor.insertText(text.rstrip('\n') + '\n\n')
        cursor.endEditBlock()
        self.window.editor.setTextCursor(cursor)
        self.window.editor.setFocus()
        self.result_cursor = None
        self.update_paste()
        self.status.setText('Inserted above the original selection. Undo is available in the document.')

    def cancel_request(self):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            self.timeout.stop()
            reply.abort()
            reply.deleteLater()
            self.requests.setEnabled(True)
            self.cancel.setEnabled(False)
            self.status.setText('Request cancelled.')

    def timed_out(self):
        self.cancel_request()
        self.status.setText('The AI request timed out. Try again.')
