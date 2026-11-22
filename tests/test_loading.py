"""File switches present fully formatted documents in one update."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow, fmt


class LoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', str(Path(settings.fileName()).parent))
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

    def test_emphasis_heavy_load_has_final_layout_and_reachable_cursor(self):
        w = self.window
        e = w.editor
        source = '# Title\n' + ''.join(
            f'**Paragraph {i}** with *italic text* and `inline code`. '
            + 'Words that wrap across the page. ' * 6 + '\n'
            for i in range(160)) + '## Last heading\nFinal paragraph.'
        path = self.load(source)
        self.assertEqual(e.textCursor().position(), 0)
        document = e.document()

        def paragraph_heights():
            block = document.firstBlock()
            heights = []
            while block.isValid():
                heights.append(document.documentLayout().blockBoundingRect(block).height())
                self.assertGreater(block.layout().lineCount(), 0)
                block = block.next()
            return heights

        initial_heights = paragraph_heights()
        self.assertTrue(all(height > 0 for height in initial_heights))
        # A fresh highlight after loading must produce the same rendered page
        # and paragraph geometry as the initial batched pass.
        e.dismiss_cursor()
        self.settle()
        initial_heights = paragraph_heights()
        initial_frame = e.viewport().grab().toImage()
        w.highlighter.rehighlight()
        self.settle()
        self.assertEqual(paragraph_heights(), initial_heights)
        self.assertEqual(e.viewport().grab().toImage(), initial_frame)

        for block_number in (80, document.blockCount() - 1):
            cursor = QTextCursor(document.findBlockByNumber(block_number))
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            e.setTextCursor(cursor)
            e.ensureCursorVisible()
            self.app.processEvents()
            self.assertEqual(e.textCursor().position(), cursor.position())
            self.assertTrue(e.viewport().rect().intersects(e.cursorRect()))
        self.assertGreater(e.verticalScrollBar().value(), 0)
        self.assertEqual(e.toPlainText(), source)
        self.assertEqual(path.read_text(), source)
        self.assertFalse(w.has_unsaved_changes())
        self.assertFalse(document.isUndoAvailable())

    def test_loaded_baseline_serializes_once_and_preserves_unicode(self):
        w = self.window
        with patch.object(w, 'document_source', wraps=w.document_source) as serialize:
            self.load('# Title 😀\nNonbreaking\u00a0space\n---\nscratch:Draft 😀\n---\nEnd')
            self.assertEqual(serialize.call_count, 1)
        self.assertEqual(w._saved_text, w.document_source())
        self.assertFalse(w.has_unsaved_changes())

    def test_batched_load_spelling_reaches_last_paragraph_and_clears_on_replacement(self):
        w = self.window
        spelling = w.editor.spelling
        spelling.set_enabled(True)
        source = '# Title\n' + '**speling** and *hello* with `typpo`.\n' * 80 + '## End\n😀 wrng'
        self.load(source)

        def finish_spelling():
            spelling.refresh()
            for _ in range(10000):
                if spelling._pending_start is None and spelling._job is None:
                    return
                spelling.process_batch()
            self.fail('Spelling did not finish')

        finish_spelling()
        selections = w.editor.extraSelections()
        self.assertEqual([s.cursor.selectedText() for s in selections], ['speling'] * 80 + ['wrng'])
        self.assertTrue(w.editor.document().isLayoutEnabled())
        self.assertFalse(w.has_unsaved_changes())
        self.assertFalse(w.editor.document().isUndoAvailable())
        self.load('Hello world', 'replacement.md')
        finish_spelling()
        self.assertEqual(w.editor.extraSelections(), [])

    def test_table_widths_are_final_before_first_paint(self):
        e = self.window.editor
        source = '| Name | Value |\n| --- | ---: |\n' + ''.join(
            f'| **Row {i}** | value {i} |\n' for i in range(120))
        with patch.object(e, 'table_cell_documents', wraps=e.table_cell_documents) as prepare:
            self.load(source)
            self.assertEqual(prepare.call_count, 121)
            self.assertFalse(e._table_pending)
            self.assertFalse(e._table_prepare_timer.isActive())
            layout = next(iter(e._table_layouts.values()))
            natural = list(layout.natural)
            first_frame = e.viewport().grab().toImage()
            self.settle()
            self.assertEqual(prepare.call_count, 121)
            self.assertEqual(layout.natural, natural)
            self.assertEqual(e.viewport().grab().toImage(), first_frame)
        self.assertEqual(e.toPlainText(), source)
        self.assertFalse(self.window.has_unsaved_changes())

    def test_large_note_search_and_headings_are_ready_before_first_paint(self):
        w = self.window
        w.open_find()
        w.find_input.setText('ordinary')
        with patch.object(w, 'update_find_matches', wraps=w.update_find_matches) as search:
            self.load('# First\n' + 'ordinary prose\n' * 500 + '## Last')
            self.assertEqual(search.call_count, 1)
            self.assertFalse(w._load_details_pending)
            self.assertEqual(len(w.find_matches), 500)
            self.assertEqual([title for _, _, title in w.headings], ['First', 'Last'])
            self.settle()
            self.assertEqual(search.call_count, 1)

    def test_tree_switch_has_no_intermediate_paint_or_later_reflow(self):
        w = self.window
        w.set_project_tree_path(self.root)
        w.toggle_project_tree()
        self.app.processEvents()
        sources = ['# First\n' + 'Ordinary prose that wraps. ' * 20 +
                   '\n' + 'Another paragraph.\n' * 500 + '## Last',
                   'Plain replacement\n' + 'Regular text.\n' * 400,
                   'Short note']
        for i, source in enumerate(sources):
            with self.subTest(i=i):
                path = self.root / f'tree-{i}.md'
                path.write_text(source)
                index = w.project_model.index(str(path))
                self.assertTrue(index.isValid())
                # Try synchronous repaints at the steps that change layout.
                # Qt must suppress them until the entire switch is complete.
                def update_headings(*args, **kwargs):
                    self.assertFalse(w.updatesEnabled())
                    self.assertFalse(w.editor.viewport().updatesEnabled())
                    headings(*args, **kwargs)
                    w.editor.viewport().repaint()

                headings = w.update_headings
                with patch.object(w, 'update_headings', side_effect=update_headings):
                    w.editor.dismiss_cursor()
                    w.project_tree.activated.emit(index)
                self.assertTrue(w.updatesEnabled())
                self.assertEqual(w.editor.toPlainText(), source)
                self.assertEqual(w.heading_list.count(), 2 if i == 0 else 0)
                self.assertEqual(w.heading_panel.isVisible(), i == 0)
                first_frame = w.editor.viewport().grab().toImage()
                geometry = w.editor.viewport().geometry()
                self.settle()
                self.assertEqual(w.editor.viewport().geometry(), geometry)
                self.assertEqual(w.editor.viewport().grab().toImage(), first_frame)
                self.assertFalse(w.has_unsaved_changes())
                self.assertNotIn('*', w.windowTitle())
                self.assertFalse(w.editor.document().isUndoAvailable())

    def test_tree_open_keeps_heading_rendered_until_document_click(self):
        w = self.window
        e = w.editor
        w.set_project_tree_path(self.root)
        w.toggle_project_tree()
        self.app.processEvents()
        def marker_alpha(block):
            ranges = block.layout().formats()
            return ranges[0].format.foreground().color().alpha()

        for i in range(2):
            with self.subTest(i=i):
                # Also cover opening the next note after editing the previous one.
                e.setFocus()
                source = f'# Title {i}\nBody text\n## Second heading'
                path = self.root / f'preview-{i}.md'
                path.write_text(source)
                w.project_tree.activated.emit(w.project_model.index(str(path)))
                self.settle()
                self.assertFalse(e.hasFocus())
                self.assertTrue(e._cursor_dismissed)
                self.assertIsNone(w.highlighter.active_block)
                first = e.document().firstBlock()
                self.assertEqual(marker_alpha(first), 0)
                self.assertFalse(w.has_unsaved_changes())
                self.assertFalse(e.document().isUndoAvailable())

                # Clicking prose must place the cursor there, without revealing
                # the heading at the top of the page.
                body = e.document().findBlockByNumber(1)
                QTest.mouseClick(e.viewport(), Qt.MouseButton.LeftButton,
                                 pos=e.cursorRect(QTextCursor(body)).center())
                self.assertTrue(e.hasFocus())
                self.assertFalse(e._cursor_dismissed)
                self.assertEqual(e.textCursor().blockNumber(), 1)
                self.assertEqual(w.highlighter.active_block, body)
                self.assertEqual(marker_alpha(first), 0)

                QTest.mouseClick(e.viewport(), Qt.MouseButton.LeftButton,
                                 pos=e.cursorRect(QTextCursor(first)).center())
                self.assertEqual(w.highlighter.active_block, first)
                self.assertEqual(marker_alpha(first), 255)
                self.assertEqual(e.toPlainText(), source)
                self.assertFalse(w.has_unsaved_changes())
                self.assertFalse(e.document().isUndoAvailable())

    def test_tree_open_preserves_tree_focus(self):
        w = self.window
        w.set_project_tree_path(self.root)
        w.toggle_project_tree()
        self.app.processEvents()
        path = self.root / 'tree-focus.md'
        path.write_text('# Title\nBody')
        self.assertTrue(w.project_tree.hasFocus())
        w.project_tree.activated.emit(w.project_model.index(str(path)))
        self.settle()
        self.assertTrue(w.project_tree.hasFocus())
        self.assertFalse(w.editor.hasFocus())
        self.assertIsNone(w.highlighter.active_block)

    def test_switch_cancels_deferred_editor_work_from_previous_document(self):
        w = self.window
        source = '| A | B |\n| - | - |\n' + '| old | cells |\n' * 120
        w.editor.setPlainText(source, defer_presentation=True)
        w.editor.update_code_panels(full=False)
        w.mark_loaded_source_saved()
        w.editor.viewport().repaint()
        self.assertTrue(w.editor._table_pending)
        self.load('Replacement', 'replacement.md')
        self.settle()
        self.assertFalse(w.editor._table_prepare_timer.isActive())
        self.assertEqual(w.editor.table_regions, [])
        self.assertEqual(w.editor.toPlainText(), 'Replacement')
        self.assertFalse(w.has_unsaved_changes())

    def test_updates_are_restored_on_load_failure(self):
        path = self.root / 'note.md'
        path.write_text('New note')
        with patch.object(self.window, 'load_document_source', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.window.open_file(path)
        self.assertTrue(self.window.updatesEnabled())
        self.assertFalse(self.window.loading)
        self.assertTrue(self.window.editor.document().isLayoutEnabled())
        self.assertEqual(self.window.editor._layout_batch_depth, 0)

    def test_layout_is_restored_when_heading_preparation_fails(self):
        path = self.root / 'note.md'
        path.write_text('# Title\n**Formatted text**\n## End\nLast paragraph')
        with patch.object(self.window, 'update_headings', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.window.open_file(path)
        editor = self.window.editor
        self.assertTrue(self.window.updatesEnabled())
        self.assertTrue(editor.document().isLayoutEnabled())
        self.assertEqual(editor._layout_batch_depth, 0)
        self.assertGreater(editor.document().documentLayout().documentSize().height(), 0)

    def test_existing_disabled_updates_are_preserved(self):
        self.window.setUpdatesEnabled(False)
        self.load('New note')
        self.assertFalse(self.window.updatesEnabled())
        self.window.setUpdatesEnabled(True)

    def test_edit_after_table_load_remains_dirty_and_undoable(self):
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
