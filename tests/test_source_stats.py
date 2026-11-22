"""Incremental totals agree with serialized source across edits and undo."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from main import MainWindow, NoteEditor


class SourceStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = NoteEditor()

    def tearDown(self):
        self.editor.deleteLater()
        self.app.processEvents()

    def assert_totals(self, saved):
        source = self.editor.toPlainText()
        self.assertEqual(self.editor.source_stats.word_count, len(source.split()))
        self.assertEqual(self.editor.source_stats.dirty, source != saved)
        self.assertEqual('\n'.join(self.editor.source_stats.blocks), source)

    def test_random_replacements_unicode_and_undo_redo(self):
        e = self.editor
        e.setPlainText('One two\n\nThree 😀 four\nFive\u00a0six\u2028seven\n')
        saved = e.toPlainText()
        e.source_stats.mark_saved()
        rng = random.Random(83)
        for _ in range(160):
            source = e.toPlainText()
            start = rng.randrange(len(source) + 1)
            end = rng.randrange(start, len(source) + 1)
            cursor = QTextCursor(e.document())
            cursor.setPosition(len(source[:start].encode('utf-16-le')) // 2)
            cursor.setPosition(len(source[:end].encode('utf-16-le')) // 2,
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.beginEditBlock()
            cursor.insertText(rng.choice(('', '\n', 'hello world', '😀\nΩ',
                                         '\t a\u00a0b\u2028c', '\n\n', '\r\n', '\u2029\u2003')))
            cursor.endEditBlock()
            self.assert_totals(saved)
        while e.document().isUndoAvailable():
            e.undo()
            self.assert_totals(saved)
        self.assertEqual(e.toPlainText(), saved)
        while e.document().isRedoAvailable():
            e.redo()
            self.assert_totals(saved)

    def test_manual_restoration_equal_length_edits_and_document_swap(self):
        e = self.editor
        e.setPlainText('old words\nlast line')
        e.source_stats.mark_saved()
        cursor = QTextCursor(e.document())
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText('new')
        self.assert_totals('old words\nlast line')
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText('old')
        self.assert_totals('old words\nlast line')
        e.setPlainText('A replacement\nwith more\nparagraphs')
        self.assert_totals('old words\nlast line')
        e.source_stats.mark_saved()
        self.assert_totals(e.toPlainText())

    def test_status_and_dirty_queries_do_not_copy_the_document(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / 'settings.ini'), QSettings.Format.IniFormat)
            settings.setValue('project_tree_path', str(Path(settings.fileName()).parent))
            settings.setValue('spell_check', False)
            with patch('main.QSettings', return_value=settings):
                window = MainWindow()
            try:
                window.editor.insertPlainText('one two\nthree')
                with patch.object(window.editor, 'toPlainText', side_effect=AssertionError('full scan')):
                    window.update_status()
                    window.update_title()
                    self.assertTrue(window.has_unsaved_changes())
                    self.assertEqual(window.count_label.text(), '3 words')
                    window.editor.undo()
                    self.assertFalse(window.has_unsaved_changes())
                    window.set_font_size(window.font_size + 1)
                    window.editor.set_paragraph_spacing(20)
                    self.assertFalse(window.has_unsaved_changes())
                    self.assertEqual(window.count_label.text(), '0 words')
                window.scratchpad_editor.insertPlainText('scratch only')
                self.assertTrue(window.has_unsaved_changes())
                self.assertEqual(window.count_label.text(), '0 words')
                window.scratchpad_editor.undo()
                self.assertFalse(window.has_unsaved_changes())
            finally:
                window._saved_text = window.document_source()
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
