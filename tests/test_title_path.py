"""The path hover card follows each tab and keeps its actions usable."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QUrl
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow


class TitlePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'a file #1.md'
        self.path.write_text('Hello')
        settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', str(Path(settings.fileName()).parent))
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow(self.path)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.popup = self.window.document_path_popup

    def tearDown(self):
        self.window._saved_text = self.window.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_hover_and_actions_preserve_editor_focus(self):
        self.assertTrue(QTest.qWaitForWindowActive(self.window))
        self.window.editor.setFocus()
        hover_timeout = QSignalSpy(self.popup.show_timer.timeout)
        QTest.mouseMove(self.window.tab_bar, self.window.tab_bar.tabRect(0).topLeft() + QPoint(10, 10))
        self.assertTrue(hover_timeout.wait(2000), 'Document path hover timer did not fire')
        self.assertTrue(self.popup.isVisible())
        self.assertEqual(self.popup.path_label.text(), str(self.path))
        self.assertIs(self.app.focusWidget(), self.window.editor)
        # Leaving the title gives time to move onto the card and its buttons.
        self.app.sendEvent(self.window.title_label, QEvent(QEvent.Type.Leave))
        self.assertTrue(self.popup.isVisible())
        self.app.sendEvent(self.popup, QEvent(QEvent.Type.Enter))
        self.assertFalse(self.popup.hide_timer.isActive())
        QTest.mouseClick(self.popup.copy_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.app.clipboard().text(), str(self.path))
        with patch('main.QDesktopServices.openUrl', return_value=True) as open_url:
            QTest.mouseClick(self.popup.folder_button, Qt.MouseButton.LeftButton)
        open_url.assert_called_once_with(QUrl.fromLocalFile(str(self.path.parent)))
        self.assertFalse(self.popup.isVisible())

    def test_hover_another_tab_updates_position_path_and_actions(self):
        other = self.path.parent / 'another folder' / 'other.md'
        other.parent.mkdir()
        other.write_text('Other')
        self.window.open_file(other)
        self.app.processEvents()
        self.window.editor.setFocus()
        bar = self.window.tab_bar
        timeout = QSignalSpy(self.popup.show_timer.timeout)
        QTest.mouseMove(bar, bar.tabRect(0).topLeft() + QPoint(10, 10))
        self.assertTrue(timeout.wait(2000))
        self.assertEqual(self.popup.path, self.path)
        self.assertEqual(self.popup.pos(), bar.mapToGlobal(bar.tabRect(0).bottomLeft()) + QPoint(0, 1))
        self.assertEqual(self.window.current_file, other)
        self.assertIs(self.app.focusWidget(), self.window.editor)

        QTest.mouseMove(bar, bar.tabRect(1).topLeft() + QPoint(10, 10))
        self.assertTrue(self.popup.isVisible())
        self.assertEqual(self.popup.path_label.text(), str(other))
        self.assertEqual(self.popup.pos(), bar.mapToGlobal(bar.tabRect(1).bottomLeft()) + QPoint(0, 1))
        QTest.mouseClick(self.popup.copy_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.app.clipboard().text(), str(other))
        with patch('main.QDesktopServices.openUrl', return_value=True) as open_url:
            QTest.mouseClick(self.popup.folder_button, Qt.MouseButton.LeftButton)
        open_url.assert_called_once_with(QUrl.fromLocalFile(str(other.parent)))

    def test_hover_unsaved_tab_and_active_title_refresh(self):
        self.window.new_file()
        bar = self.window.tab_bar
        timeout = QSignalSpy(self.popup.show_timer.timeout)
        QTest.mouseMove(bar, bar.tabRect(0).topLeft() + QPoint(10, 10))
        self.assertTrue(timeout.wait(2000))
        self.window.editor.insertPlainText('Draft')
        self.assertEqual(self.popup.path, self.path)
        QTest.mouseMove(bar, bar.tabRect(1).topLeft() + QPoint(10, 10))
        self.assertEqual(self.popup.path_label.text(), 'Not saved yet')
        self.assertFalse(self.popup.copy_button.isEnabled())
        self.assertFalse(self.popup.folder_button.isEnabled())

    def test_blank_tab_bar_space_does_not_show_card(self):
        bar = self.window.tab_bar
        QTest.mouseMove(bar, QPoint(bar.width() - 5, bar.height() // 2))
        self.assertFalse(self.popup.show_timer.isActive())
        self.assertFalse(self.popup.isVisible())

    def test_switch_new_and_save_as_refresh_path(self):
        other = self.path.with_name('other.txt')
        other.write_text('Other')
        self.window.open_file(other)
        self.assertEqual(self.popup.path_label.text(), str(other))
        self.window.new_file()
        self.assertEqual(self.popup.path_label.text(), 'Not saved yet')
        self.assertFalse(self.popup.copy_button.isEnabled())
        self.assertFalse(self.popup.folder_button.isEnabled())
        saved = self.path.with_name('saved.md')
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(saved), 'All files (*)')):
            self.assertTrue(self.window.save_as())
        self.assertEqual(self.popup.path_label.text(), str(saved))
        self.assertTrue(self.popup.copy_button.isEnabled())
        self.assertTrue(self.popup.folder_button.isEnabled())

    def test_escape_move_and_close_dismiss_card(self):
        self.popup.show_for_title()
        QTest.keyClick(self.window.editor, Qt.Key.Key_Escape)
        self.assertFalse(self.popup.isVisible())
        self.popup.show_for_title()
        self.window.move(self.window.x() + 10, self.window.y() + 10)
        self.app.processEvents()
        self.assertFalse(self.popup.isVisible())
        self.popup.show_for_title()
        self.window.close()
        self.assertFalse(self.popup.isVisible())

    def test_leaving_card_dismisses_after_grace_period(self):
        self.popup.show_for_title()
        outside = self.window.editor.mapToGlobal(QPoint(50, 200))
        hide_timeout = QSignalSpy(self.popup.hide_timer.timeout)
        with patch('main.QCursor.pos', return_value=outside):
            self.app.sendEvent(self.popup, QEvent(QEvent.Type.Leave))
            self.assertTrue(self.popup.isVisible())
            self.assertTrue(hide_timeout.wait(2000), 'Document path hide timer did not fire')
        self.assertFalse(self.popup.isVisible())


if __name__ == '__main__':
    unittest.main()
