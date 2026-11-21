"""Documents in the title row keep independent editing state and close safely."""
import codecs
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from main import MainWindow


class TabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.first, self.second = root / 'first.md', root / 'second.md'
        self.first.write_bytes(codecs.BOM_UTF8 + b'# First\r\nBody\r\n')
        self.second.write_text('# Second\nOther text')
        settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow(self.first)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._updating = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_tabs_share_menu_row_and_click_switches_without_duplicates(self):
        w = self.window
        w.open_file(self.second)
        self.app.processEvents()
        self.assertIs(w.tab_bar.parentWidget(), w.menuBar())
        self.assertEqual(w.tab_bar.count(), 2)
        self.assertLess(w.tab_bar.geometry().right(), w.minimize_button.mapTo(w.menuBar(), w.minimize_button.rect().topLeft()).x())
        QTest.mouseClick(w.tab_bar, Qt.MouseButton.LeftButton, pos=w.tab_bar.tabRect(0).center())
        self.assertEqual(w.current_file, self.first)
        w.open_file(self.second)
        self.assertEqual(w.tab_bar.count(), 2)
        self.assertEqual(w.tab_bar.currentIndex(), 1)

    def test_each_tab_keeps_scratchpad_undo_selection_and_file_encoding(self):
        w = self.window
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        w.editor.insertPlainText('More')
        cursor = w.editor.document().find('Body')
        w.editor.setTextCursor(cursor)
        w.scratchpad_editor.insertPlainText('Scratch one')
        w.open_file(self.second)
        self.assertEqual(w.scratchpad_editor.toPlainText(), '')
        self.assertFalse(w.has_bom)
        self.assertFalse(w.has_unsaved_changes())
        w.scratchpad_editor.insertPlainText('Scratch two')
        w.activate_tab(0)
        self.assertEqual(w.editor.textCursor().selectedText(), 'Body')
        self.assertEqual(w.scratchpad_editor.toPlainText(), 'Scratch one')
        self.assertTrue(w.has_bom)
        self.assertEqual(w.newline, '\r\n')
        self.assertTrue(w.has_unsaved_changes())
        self.assertTrue(w.tab_bar.tabText(0).endswith('*'))
        w.scratchpad_editor.undo()
        self.assertEqual(w.scratchpad_editor.toPlainText(), '')
        w.editor.undo()
        self.assertFalse(w.has_unsaved_changes())
        w.activate_tab(1)
        self.assertEqual(w.scratchpad_editor.toPlainText(), 'Scratch two')
        self.assertTrue(w.has_unsaved_changes())

    def test_close_cancel_save_failure_and_discard(self):
        w = self.window
        w.editor.insertPlainText('Draft')
        w.open_file(self.second)
        for choice in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save):
            with patch.object(QMessageBox, 'exec', return_value=choice), patch.object(w, 'save_file', return_value=False):
                self.assertFalse(w.close_tab(0))
            self.assertEqual(w.tab_bar.count(), 2)
            self.assertEqual(w.current_file, self.first)
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(w.close_tab(0))
        self.assertEqual(w.current_file, self.second)
        self.assertEqual(w.tab_bar.count(), 1)
        self.assertTrue(w.close_tab())
        self.assertEqual(w.tab_bar.count(), 1)
        self.assertIsNone(w.current_file)
        self.assertEqual(w.editor.toPlainText(), '')

    def test_close_window_prompts_for_inactive_dirty_tab(self):
        w = self.window
        w.editor.insertPlainText('Draft')
        w.open_file(self.second)
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Cancel) as prompt:
            self.assertFalse(w.close())
        prompt.assert_called_once()
        self.assertEqual(w.current_file, self.first)
        self.assertTrue(w.has_unsaved_changes())
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save):
            self.assertTrue(w.close())
        self.assertIn(b'Draft', self.first.read_bytes())

    def test_drop_opens_all_files_and_shortcuts_cycle_tabs(self):
        w = self.window
        w.open_dropped([str(self.second), str(self.first)])
        self.assertEqual(w.tab_bar.count(), 2)
        QTest.keyClick(w.editor, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.current_file, self.second)
        QTest.keyClick(w.editor, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(w.current_file, self.first)

    def test_scroll_and_save_belong_to_selected_document(self):
        w = self.window
        self.first.write_text('# First\n' + 'A paragraph\n' * 100)
        w.reload_document()
        self.app.processEvents()
        w.editor.verticalScrollBar().setValue(450)
        scroll = w.editor.verticalScrollBar().value()
        w.open_file(self.second)
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        w.editor.insertPlainText('\nNew second paragraph')
        self.assertTrue(w.save_file())
        self.assertTrue(self.second.read_text().endswith('New second paragraph'))
        w.activate_tab(0)
        self.assertEqual(w.editor.verticalScrollBar().value(), scroll)
        self.assertFalse(w.has_unsaved_changes())
        self.assertFalse(self.first.read_text().endswith('New second paragraph'))

    def test_empty_scratchpads_are_independent(self):
        w = self.window
        w.open_file(self.second)
        w.scratchpad_editor.insertPlainText('Only the second file')
        w.activate_tab(0)
        self.assertEqual(w.scratchpad_editor.toPlainText(), '')
        self.assertFalse(w.has_unsaved_changes())
        w.activate_tab(1)
        self.assertEqual(w.scratchpad_editor.toPlainText(), 'Only the second file')
        self.assertTrue(w.has_unsaved_changes())

    def click_tree_file(self, path, modifiers=Qt.KeyboardModifier.NoModifier):
        w = self.window
        w.set_project_tree_path(self.first.parent)
        if not w.project_panel.isVisible():
            w.toggle_project_tree()
        for _ in range(50):
            QTest.qWait(10)
            index = w.project_model.index(str(path))
            if (w.project_tree.visualRect(index).isValid()
                    and w.project_tree.indexAt(w.project_tree.visualRect(index).center()) == index):
                break
        w.project_tree.scrollTo(index)
        self.assertEqual(w.project_tree.indexAt(w.project_tree.visualRect(index).center()), index)
        QTest.mouseClick(w.project_tree.viewport(), Qt.MouseButton.LeftButton,
                         modifiers, w.project_tree.visualRect(index).center())

    def test_tree_click_replaces_active_tab_and_ctrl_click_keeps_draft(self):
        w = self.window
        w.editor.insertPlainText('Draft')
        with patch.object(QMessageBox, 'exec') as prompt:
            self.click_tree_file(self.second, Qt.KeyboardModifier.ControlModifier)
        prompt.assert_not_called()
        self.assertEqual(w.tab_bar.count(), 2)
        self.assertEqual(w.current_file, self.second)
        w.activate_tab(0)
        self.assertIn('Draft', w.editor.toPlainText())
        third = self.first.with_name('third.md')
        third.write_text('# Third')
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
            self.click_tree_file(third)
        self.assertEqual(w.tab_bar.count(), 2)
        self.assertEqual(w.current_file, third)
        self.assertEqual([tab['path'] for tab in w._tabs], [third, self.second])
        self.assertTrue(w.project_tree.hasFocus())
        self.assertFalse(w.has_unsaved_changes())

    def test_tree_replacement_saves_or_cancels_and_handles_existing_tab(self):
        w = self.window
        w.editor.insertPlainText('Draft')
        for choice in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save):
            with patch.object(QMessageBox, 'exec', return_value=choice), patch.object(w, 'save_file', return_value=False):
                self.click_tree_file(self.second)
            self.assertEqual(w.current_file, self.first)
            self.assertEqual(w.tab_bar.count(), 1)
            self.assertIn('Draft', w.editor.toPlainText())
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save):
            self.click_tree_file(self.second)
        self.assertIn(b'Draft', self.first.read_bytes())
        self.assertEqual(w.current_file, self.second)
        self.assertEqual(w.tab_bar.count(), 1)
        self.click_tree_file(self.first, Qt.KeyboardModifier.ControlModifier)
        self.click_tree_file(self.second)
        self.assertEqual(w.tab_bar.count(), 1)
        self.assertEqual(w.current_file, self.second)
        self.assertTrue(w.project_tree.hasFocus())

    def test_failed_replacement_keeps_current_document(self):
        w = self.window
        w.editor.insertPlainText('Draft')
        with patch.object(QMessageBox, 'critical'), patch.object(QMessageBox, 'exec') as prompt:
            self.assertFalse(w.open_file(self.first.with_name('missing.md'), replace_current=True))
        prompt.assert_not_called()
        self.assertEqual(w.current_file, self.first)
        self.assertEqual(w.tab_bar.count(), 1)
        self.assertIn('Draft', w.editor.toPlainText())
