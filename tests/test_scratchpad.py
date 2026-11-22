"""Scratch metadata is edited separately and preserved in the note on disk."""
import codecs
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from main import MainWindow, split_scratchpad


SCRATCH = '# hi\nWhere are we?\n- in\n- th\n- way'
BLOCK = '---\nscratch:' + SCRATCH + '\n---\n'


class ScratchpadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'note.md'
        self.path.write_text(BLOCK + '# Main\nVisible words\n')
        settings = QSettings(str(self.path.with_suffix('.ini')), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', str(Path(settings.fileName()).parent))
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow(self.path)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._saved_text = self.window.document_source()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_example_is_hidden_from_document_and_shown_on_left(self):
        w = self.window
        self.assertEqual(w.scratchpad_editor.toPlainText(), SCRATCH)
        self.assertEqual(w.editor.toPlainText(), '# Main\nVisible words\n')
        self.assertEqual(w.count_label.text(), '4 words')
        self.assertFalse(w.has_unsaved_changes())
        self.assertFalse(w.scratchpad_panel.isVisible())
        w.ribbon_buttons['Scatchpad'].click()
        self.app.processEvents()
        self.assertTrue(w.scratchpad_panel.isVisible())
        self.assertLess(w.scratchpad_panel.mapTo(w, QPoint()).x(),
                        w.editor.mapTo(w, QPoint()).x())
        w.open_find()
        w.find_input.setText('Where are we?')
        self.assertEqual(w.find_matches, [])
        w.ribbon_buttons['Scatchpad'].click()
        self.assertFalse(w.scratchpad_panel.isVisible())

    def test_round_trip_and_main_edits_preserve_block(self):
        w = self.window
        original = self.path.read_bytes()
        self.assertTrue(w.save_file())
        self.assertEqual(self.path.read_bytes(), original)
        w.editor.moveCursor(QTextCursor.MoveOperation.Start)
        w.editor.insertPlainText('New paragraph\n')
        self.assertTrue(w.save_file())
        self.assertEqual(self.path.read_text(), BLOCK + 'New paragraph\n# Main\nVisible words\n')

    def test_scratch_edits_survive_new_tab_and_save_undo(self):
        w = self.window
        w.scratchpad_editor.moveCursor(QTextCursor.MoveOperation.End)
        w.scratchpad_editor.insertPlainText('\nAnother thought')
        self.assertTrue(w.has_unsaved_changes())
        with patch.object(QMessageBox, 'exec') as prompt:
            w.new_file()
            self.assertEqual(w.scratchpad_editor.toPlainText(), '')
            w.activate_tab(0)
        prompt.assert_not_called()
        self.assertEqual(w.current_file, self.path)
        w.scratchpad_editor.undo()
        self.assertFalse(w.has_unsaved_changes())
        w.scratchpad_editor.redo()
        self.assertTrue(w.save_file())
        self.assertIn('Another thought\n---\n# Main', self.path.read_text())
        self.assertFalse(w.has_unsaved_changes())
        self.assertTrue(w.reload_document())
        self.assertTrue(w.scratchpad_editor.toPlainText().endswith('Another thought'))
        w.new_file()
        self.assertEqual(w.scratchpad_editor.toPlainText(), '')
        self.assertEqual(w.document_source(), '')

    def test_new_scratch_block_and_crlf_bom(self):
        w = self.window
        self.path.write_bytes(codecs.BOM_UTF8 + b'Visible\r\n')
        self.assertTrue(w.reload_document())
        w.scratchpad_editor.insertPlainText('New scratch')
        self.assertTrue(w.save_file())
        self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8 +
                         b'---\r\nscratch:New scratch\r\n---\r\nVisible\r\n')

    def test_mid_document_block_and_unicode_round_trip(self):
        source = 'Hello 🌍\n\n' + BLOCK + '\nEnd'
        self.path.write_text(source)
        self.assertTrue(self.window.reload_document())
        self.assertEqual(self.window.document_source(), source)
        self.assertTrue(self.window.save_file())
        self.assertEqual(self.path.read_text(), source)

    def test_non_metadata_is_preserved(self):
        for source in ('---\ntitle: hello\n---\nBody',
                       '---\nscratch:unfinished',
                       '```markdown\n' + BLOCK + '```\n',
                       '~~~\n' + BLOCK + '~~~\n'):
            with self.subTest(source=source):
                self.assertEqual(split_scratchpad(source), (source, '', '', 0))
        text_file = self.path.with_suffix('.txt')
        text_file.write_text(BLOCK)
        self.assertTrue(self.window.open_file(text_file))
        self.assertEqual(self.window.editor.toPlainText(), BLOCK)
        self.assertEqual(self.window.scratchpad_editor.toPlainText(), '')
