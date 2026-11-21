"""Loading performs one highlight and safely defers offscreen presentation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow, TableCells, TableLayout, fmt


class LoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('spell_check', False)
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.mark_loaded_source_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def load(self, source, name='note.md'):
        path = self.root / name
        path.write_text(source)
        self.assertTrue(self.window.open_file(path))
        return path

    def settle(self):
        for _ in range(1000):
            self.app.processEvents()
            if not (self.window._load_details_pending or
                    self.window.editor._table_prepare_timer.isActive() or
                    self.window.editor._awaiting_first_paint):
                return
            QTest.qWait(1)
        self.fail('Loading did not finish')

    def test_one_highlight_pass_without_delayed_second_pass(self):
        w = self.window
        with patch.object(w.highlighter, 'highlightBlock',
                          wraps=w.highlighter.highlightBlock) as blocks:
            self.load('# First\n' + 'Ordinary prose.\n' * 500 + '## Last')
            self.settle()
            self.assertLessEqual(blocks.call_count, w.editor.document().blockCount() + 2)
        self.assertFalse(w.has_unsaved_changes())
        self.assertFalse(w.editor.document().isUndoAvailable())

    def test_empty_scratchpad_is_not_replaced(self):
        with patch.object(self.window.scratchpad_editor, 'setPlainText') as replace:
            self.load('A note without scratch metadata')
            replace.assert_not_called()

    def test_loaded_baseline_serializes_once_and_preserves_unicode(self):
        w = self.window
        with patch.object(w, 'document_source', wraps=w.document_source) as serialize:
            self.load('# Title 😀\nNonbreaking\u00a0space\n---\nscratch:Draft 😀\n---\nEnd')
            self.assertEqual(serialize.call_count, 1)
        self.assertEqual(w._saved_text, w.document_source())
        self.assertFalse(w.has_unsaved_changes())

    def test_offscreen_table_cells_are_deferred_and_final_widths_are_exact(self):
        e = self.window.editor
        source = '| Name | Value |\n| --- | ---: |\n' + ''.join(
            f'| **Row {i}** | value {i} |\n' for i in range(120))
        with patch.object(e, 'table_cell_documents', wraps=e.table_cell_documents) as prepare:
            self.load(source)
            self.assertEqual(prepare.call_count, 0)
            e.viewport().repaint()
            self.assertGreater(prepare.call_count, 0)
            self.assertLess(prepare.call_count, 121)
            self.settle()
            self.assertEqual(prepare.call_count, 121)
        layout = next(iter(e._table_layouts.values()))
        self.assertTrue(all(isinstance(cells, TableCells) and cells.documents is not None
                            for _, cells in layout.rows))
        eager = TableLayout(layout.alignment,
                            [(pos, e.table_cell_documents(cells.record))
                             for pos, cells in layout.rows])
        self.assertEqual(layout.natural, eager.natural)
        self.assertEqual(e.toPlainText(), source)
        self.assertFalse(e._defer_tables)

    def test_large_note_search_and_headings_wait_for_first_paint(self):
        w = self.window
        w.open_find()
        w.find_input.setText('ordinary')
        with patch.object(w, 'update_find_matches', wraps=w.update_find_matches) as search:
            self.load('# First\n' + 'ordinary prose\n' * 500 + '## Last')
            search.assert_not_called()
            self.assertTrue(w._load_details_pending)
            self.settle()
            self.assertEqual(search.call_count, 1)
        self.assertEqual(len(w.find_matches), 500)
        self.assertEqual([title for _, _, title in w.headings], ['First', 'Last'])

    def test_switch_cancels_deferred_work_from_previous_document(self):
        w = self.window
        self.load('# First\n' + 'Old content\n' * 500 + '## Last')
        self.assertTrue(w._load_details_pending)
        self.load('New plain text', 'next.txt')
        self.settle()
        self.assertEqual(w.editor.toPlainText(), 'New plain text')
        self.assertEqual(w.headings, [])
        self.assertFalse(w._load_details_timer.isActive())
        self.assertFalse(w.editor._table_pending)
        self.assertFalse(w.has_unsaved_changes())

    def test_switch_cancels_partially_prepared_table(self):
        e = self.window.editor
        source = '| A | B |\n| - | - |\n' + '| old | cells |\n' * 120
        with patch.object(e, 'table_cell_documents', wraps=e.table_cell_documents) as prepare:
            self.load(source)
            e.viewport().repaint()
            prepared = prepare.call_count
            self.assertGreater(prepared, 0)
            self.assertTrue(e._table_pending)
            self.load('Replacement', 'replacement.md')
            self.settle()
            self.assertEqual(prepare.call_count, prepared)
        self.assertFalse(e._table_prepare_timer.isActive())
        self.assertEqual(e.table_regions, [])
        self.assertEqual(e.toPlainText(), 'Replacement')

    def test_direct_document_replacement_cancels_pending_details(self):
        w = self.window
        self.load('# First\n' + 'Old content\n' * 500 + '## Last')
        w.editor.setPlainText('# Replacement')
        self.assertFalse(w._load_details_pending)
        self.assertFalse(w._load_details_timer.isActive())
        self.assertEqual([title for _, _, title in w.headings], ['Replacement'])

    def test_edit_during_deferred_table_preparation_remains_dirty_and_undoable(self):
        e = self.window.editor
        source = '| A | B |\n| - | - |\n' + '| old | cells |\n' * 120
        self.load(source)
        cursor = e.document().find('old')
        cursor.insertText('new')
        self.settle()
        self.assertTrue(self.window.has_unsaved_changes())
        self.assertIn('| new | cells |', e.toPlainText())
        e.undo()
        self.settle()
        self.assertFalse(self.window.has_unsaved_changes())
        self.assertEqual(e.toPlainText(), source)

    def test_cached_formats_are_independent_values(self):
        original = fmt('#123456', bold=True)
        changed = fmt('#123456', bold=True)
        changed.setFontItalic(True)
        self.assertFalse(original.fontItalic())
        self.assertFalse(fmt('#123456', bold=True).fontItalic())


if __name__ == '__main__':
    unittest.main()
