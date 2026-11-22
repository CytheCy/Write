"""Tree colors persist in notes without saving or disturbing pending edits."""
import codecs
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QContextMenuEvent, QPalette, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from main import MainWindow
from project_colors import PALETTE, color_header, split_project_color
from project_search import search_project
from threading import Event


class ProjectColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'note.md'
        self.original = '---\ntitle: Note\n---\n# Hello 😀\nVisible words\n'
        self.path.write_text(self.original)
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', str(self.root))
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow(self.path)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._updating = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_popup_swatches_apply_and_default_resets(self):
        w = self.window
        w.toggle_project_tree()
        index = w.project_model.index(str(self.path))
        w.project_tree.scrollTo(index)
        self.app.processEvents()
        viewport = w.project_tree.viewport()
        position = w.project_tree.visualRect(index).center()
        # Deliver the event a desktop right-click sends to the viewport. Calling
        # the slot directly would miss broken context-menu policy or wiring.
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, position,
                                  viewport.mapToGlobal(position))
        QApplication.sendEvent(viewport, event)
        popup = w._project_color_popup
        self.assertTrue(popup.isVisible())
        QTest.mouseClick(popup.swatches[5], Qt.MouseButton.LeftButton)
        self.assertEqual(self.path.read_text(), color_header(PALETTE[5][1]) + self.original)
        self.assertFalse(w.has_unsaved_changes())
        self.assertEqual(w.editor.toPlainText(), self.original)
        self.assertEqual(w.project_model.file_color(index), PALETTE[5][1])
        w.show_project_color_popup(w.project_tree.visualRect(index).center())
        self.assertTrue(w._project_color_popup.swatches[5].isChecked())
        w._project_color_popup.default_button.click()
        self.assertEqual(self.path.read_text(), self.original)
        self.assertIsNone(w.project_model.file_color(index))

    def test_open_dirty_document_keeps_edits_undo_and_scratch(self):
        w = self.window
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        w.editor.insertPlainText('Pending prose')
        w.scratchpad_editor.insertPlainText('Pending scratch')
        self.assertTrue(w.set_project_file_color(self.path, '#528fdf'))
        self.assertEqual(self.path.read_text(), color_header('#528fdf') + self.original)
        self.assertTrue(w.has_unsaved_changes())
        w.editor.undo()
        w.scratchpad_editor.undo()
        self.assertFalse(w.has_unsaved_changes())
        w.editor.redo()
        w.scratchpad_editor.redo()
        self.assertTrue(w.save_file())
        self.assertIn('Pending prose', self.path.read_text())
        self.assertIn('scratch:Pending scratch', self.path.read_text())
        self.assertTrue(w.reload_document())
        self.assertNotIn('write-project-color', w.editor.toPlainText())
        self.assertEqual(w.scratchpad_editor.toPlainText(), 'Pending scratch')

    def test_inactive_tab_and_search_offsets_keep_metadata(self):
        w = self.window
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        w.editor.insertPlainText('Unsaved 😀 tail')
        w.new_file()
        w.editor.insertPlainText('Other tab')
        self.assertTrue(w.set_project_file_color(self.path, '#ae6acc'))
        self.assertEqual(w.editor.toPlainText(), 'Other tab')
        self.assertIn('Unsaved 😀 tail', w.project_search_snapshots()[self.path])
        self.assertTrue(w.project_search_snapshots()[self.path].startswith(color_header('#ae6acc')))
        w.activate_tab(0)
        self.assertTrue(w.has_unsaved_changes())
        w.editor.undo()
        self.assertFalse(w.has_unsaved_changes())
        w.project_search.input.setText('Visible')
        match = search_project(self.root, 'Visible', Event())[0][0]
        w.open_project_match(match)
        self.assertEqual(w.editor.textCursor().selectedText(), 'Visible')
        self.assertTrue(w.save_file())
        self.assertEqual(self.path.read_text(), color_header('#ae6acc') + self.original)

    def test_closed_file_bom_crlf_roundtrip_and_reload(self):
        w = self.window
        path = self.root / 'closed.MD'
        body = codecs.BOM_UTF8 + b'# Closed\r\n\r\nText\r\n'
        path.write_bytes(body)
        self.assertTrue(w.set_project_file_color(path, '#e05252'))
        self.assertEqual(path.read_bytes(), codecs.BOM_UTF8 +
                         color_header('#e05252').replace('\n', '\r\n').encode() + body[3:])
        w.open_file(path)
        self.assertEqual(w.editor.toPlainText(), '# Closed\n\nText\n')
        self.assertTrue(w.save_file())
        self.assertTrue(w.set_project_file_color(path, None))
        self.assertEqual(path.read_bytes(), body)

    def test_delegate_colors_name_and_icon_even_when_selected(self):
        w = self.window
        w.set_project_file_color(self.path, '#48a868')
        index = w.project_model.index(str(self.path))
        for selected in (False, True):
            option = QStyleOptionViewItem()
            option.initFrom(w.project_tree)
            option.decorationSize = QSize(16, 16)
            if selected:
                option.state |= QStyle.StateFlag.State_Selected
            w.project_tree.itemDelegate().initStyleOption(option, index)
            self.assertEqual(option.palette.color(QPalette.ColorRole.Text).name(), '#48a868')
            self.assertEqual(option.palette.color(QPalette.ColorRole.HighlightedText).name(), '#48a868')
            self.assertFalse(option.icon.isNull())

    def test_failures_do_not_change_open_document_and_examples_are_untouched(self):
        w = self.window
        before = w.document_source()
        with patch('main.QSaveFile.open', return_value=False), patch('main.QMessageBox.warning') as warning:
            self.assertFalse(w.set_project_file_color(self.path, '#528fdf'))
        warning.assert_called_once()
        self.assertEqual(w.document_source(), before)
        self.assertEqual(self.path.read_text(), self.original)
        for source in ('```md\n' + color_header('#528fdf') + '```\n',
                       '<!-- write-project-color: invalid -->\nBody'):
            self.assertEqual(split_project_color(source), (source, ''))
        index = w.project_model.index(str(self.root))
        w.show_project_color_popup(w.project_tree.visualRect(index).center())
        self.assertIsNone(getattr(w, '_project_color_popup', None))


if __name__ == '__main__':
    unittest.main()
