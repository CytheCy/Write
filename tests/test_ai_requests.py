"""Exercise AI delivery and insertion without sending private data to a service."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidgetItem

from ai_requests import AIPanel, RequestDialog, build_payload, response_text
from main import MainWindow


class PayloadTests(unittest.TestCase):
    def test_instructions_target_and_attachments_are_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            text = Path(folder) / 'facts.md'
            text.write_text('Supporting facts', encoding='utf-8')
            image = Path(folder) / 'figure.png'
            image.write_bytes(b'image bytes')
            pdf = Path(folder) / 'reference.pdf'
            pdf.write_bytes(b'pdf bytes')
            payload = build_payload('model', 'Rewrite this', 'Original passage', [text, image, pdf])
        self.assertEqual(payload['model'], 'model')
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': 'Rewrite this'})
        parts = payload['messages'][1]['content']
        self.assertIn('Original passage', parts[0]['text'])
        self.assertIn('Supporting facts', parts[1]['text'])
        self.assertTrue(parts[2]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(parts[3]['file']['filename'], 'reference.pdf')

    def test_binary_attachments_and_oversize_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'binary.bin'
            path.write_bytes(b'\x00\xff')
            with self.assertRaises(ValueError):
                build_payload('model', 'prompt', 'selected', [path])
            with patch('ai_requests.MAX_ATTACHMENT_BYTES', 1):
                with self.assertRaises(ValueError):
                    build_payload('model', 'prompt', 'selected', [path])

    def test_missing_empty_and_refused_responses(self):
        for response in ({}, {'choices': []}, {'choices': [{'message': {'content': ''}}]},
                         {'choices': [{'message': {'content': None, 'refusal': 'Refused'}}]}):
            with self.subTest(response=response), self.assertRaises(ValueError):
                response_text(response)


class AITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            QSettings.setPath(format, QSettings.Scope.UserScope, self.temp.name)
        locator = QSettings('Write', 'Write')
        locator.clear()
        locator.setValue('project_tree_path', self.temp.name)
        self.window = MainWindow()
        self.window.show()
        self.panel = self.window.ai_panel
        self.window.editor.setPlainText('Before\nSelected passage\nAfter')
        cursor = self.window.editor.textCursor()
        cursor.setPosition(7)
        cursor.setPosition(23, QTextCursor.MoveMode.KeepAnchor)
        self.window.editor.setTextCursor(cursor)
        self.window.ribbon_buttons['AI'].click()
        self.panel.insert_request('Rewrite', 'Improve the selected passage.')
        self.key = Path(self.temp.name) / 'api.txt'
        self.key.write_text('test-key')
        self.window.settings.setValue('ai/key_file', str(self.key))
        self.window.settings.setValue('ai/model', 'test-model')

    def tearDown(self):
        self.window._updating = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def serve(self, status=200, response=None, delay=0):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                body = inner.rfile.read(int(inner.headers['Content-Length']))
                received.append((inner.path, inner.headers.get('Authorization'), json.loads(body)))
                time.sleep(delay)
                inner.send_response(status)
                inner.send_header('Content-Type', 'application/json')
                inner.end_headers()
                try:
                    inner.wfile.write(json.dumps(response or {
                        'choices': [{'message': {'content': 'Improved passage'}}]}).encode())
                except BrokenPipeError:
                    pass
            def log_message(self, *_args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.window.settings.setValue('ai/endpoint', f'http://127.0.0.1:{server.server_port}/chat/completions')
        return received

    def finish(self):
        deadline = time.monotonic() + 5
        while self.panel.reply is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNone(self.panel.reply)

    def result(self):
        self.panel.result_cursor = QTextCursor(self.panel.cursor)
        self.panel.result_selection = self.panel.selected_text
        self.panel.output.setPlainText('Improved passage')

    def test_delivery_result_and_undo(self):
        received = self.serve()
        attachment = Path(self.temp.name) / 'facts.txt'
        attachment.write_text('Useful facts')
        item = QListWidgetItem('facts.txt')
        item.setData(Qt.ItemDataRole.UserRole, str(attachment))
        self.panel.attachments.addItem(item)
        self.panel.requests.itemClicked.emit(self.panel.requests.item(0))
        self.finish()
        self.assertEqual(received[0][0:2], ('/chat/completions', 'Bearer test-key'))
        self.assertEqual(received[0][2]['messages'][0]['content'], 'Improve the selected passage.')
        parts = received[0][2]['messages'][1]['content']
        self.assertIn('Selected passage', parts[0]['text'])
        self.assertIn('Useful facts', parts[1]['text'])
        self.assertEqual(self.panel.output.toPlainText(), 'Improved passage')
        self.assertTrue(self.panel.paste.isEnabled())
        self.panel.paste.click()
        self.assertEqual(self.window.editor.toPlainText(), 'Before\nImproved passage\n\nSelected passage\nAfter')
        self.window.editor.undo()
        self.assertEqual(self.window.editor.toPlainText(), 'Before\nSelected passage\nAfter')

    def test_paste_tracks_edits_before_selection(self):
        self.result()
        cursor = QTextCursor(self.window.editor.document())
        cursor.insertText('Earlier text\n')
        self.panel.paste.click()
        self.assertIn('Earlier text\nBefore\nImproved passage\n\nSelected passage', self.window.editor.toPlainText())

    def test_changed_selection_and_other_documents_cannot_receive_result(self):
        self.result()
        self.window.editor.setPlainText('A different document')
        self.panel.paste.click()
        self.assertEqual(self.window.editor.toPlainText(), 'A different document')
        self.assertIn('original selection changed', self.panel.status.text())

    def test_returning_to_original_tab_allows_insertion(self):
        self.result()
        self.window.new_file()
        self.window.editor.setPlainText('Other tab')
        self.panel.paste.click()
        self.assertEqual(self.window.editor.toPlainText(), 'Other tab')
        self.window.activate_tab(0)
        self.panel.paste.click()
        self.assertEqual(self.window.editor.toPlainText(), 'Before\nImproved passage\n\nSelected passage\nAfter')

    def test_editing_target_prevents_insertion(self):
        self.result()
        cursor = QTextCursor(self.panel.cursor)
        cursor.insertText('Changed')
        before = self.window.editor.toPlainText()
        self.panel.paste.click()
        self.assertEqual(self.window.editor.toPlainText(), before)

    def test_errors_allow_retry_and_never_enable_paste(self):
        self.serve(status=401)
        self.panel.run_request(self.panel.requests.item(0))
        self.finish()
        self.assertIn('401', self.panel.status.text())
        self.assertFalse(self.panel.paste.isEnabled())
        self.assertTrue(self.panel.requests.isEnabled())

    def test_cancel_does_not_publish_late_results(self):
        self.serve(delay=.15)
        self.panel.run_request(self.panel.requests.item(0))
        self.panel.cancel_request()
        QTest.qWait(200)
        self.assertIsNone(self.panel.reply)
        self.assertEqual(self.panel.output.toPlainText(), '')
        self.assertFalse(self.panel.paste.isEnabled())

    def test_saved_requests_and_settings_survive_panel_recreation(self):
        self.panel.save_requests()
        other = AIPanel(self.window)
        self.assertEqual(other.requests.item(0).text(), 'Rewrite')
        self.assertEqual(other.requests.item(0).data(Qt.ItemDataRole.UserRole), 'Improve the selected passage.')
        other.deleteLater()
        self.window.show_settings()
        settings = self.window.settings_dialog
        settings.ai_model.setText('another-model')
        settings.ai_model.editingFinished.emit()
        self.assertEqual(self.window.settings.value('ai/model'), 'another-model')
        settings.close()

    def test_request_dialog_requires_name_and_prompt(self):
        dialog = RequestDialog(self.panel)
        self.assertFalse(dialog.save.isEnabled())
        dialog.name.setText('Request')
        self.assertFalse(dialog.save.isEnabled())
        dialog.prompt.setPlainText('Do this')
        self.assertTrue(dialog.save.isEnabled())
        dialog.deleteLater()

    def test_no_selection_or_key_does_not_send(self):
        self.panel.cursor = None
        self.panel.run_request(self.panel.requests.item(0))
        self.assertIsNone(self.panel.reply)
        self.assertIn('Select text', self.panel.status.text())
        self.panel.capture_selection()
        self.window.settings.setValue('ai/key_file', '')
        self.panel.run_request(self.panel.requests.item(0))
        self.assertIsNone(self.panel.reply)
        self.assertIn('Settings', self.panel.status.text())
