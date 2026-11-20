"""Toolbar ribbon and persisted auto-hide behavior."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QAbstractAnimation, QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QApplication, QCheckBox, QMessageBox, QPushButton,
                               QRadioButton, QTableWidget, QToolButton)

from main import MainWindow


class RibbonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.temp.name)
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        QSettings('Write', 'Write').clear()
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        QTest.mouseMove(self.window.editor.viewport(), QPoint(200, 150))

    def tearDown(self):
        self.window._saved_text = self.window.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_ribbon_is_left_and_shows_scratchpad_and_references(self):
        w = self.window
        self.assertTrue(w.ribbon.isVisible())
        self.assertLess(w.ribbon.mapTo(w, QPoint()).x(), w.editor.mapTo(w, QPoint()).x())
        buttons = w.ribbon.findChildren(QToolButton)
        self.assertEqual(len(buttons), 6)
        self.assertEqual(buttons[0].icon_name, 'folder-open')
        self.assertEqual(buttons[0].accessibleName(), 'Project tree')
        self.assertEqual(buttons[1].icon_name, 'notepad')
        self.assertEqual(buttons[1].accessibleName(), 'Scatchpad')
        self.assertGreater(buttons[1].y(), buttons[0].y())
        self.assertEqual(buttons[2].icon_name, 'sort-a-z')
        self.assertEqual(buttons[2].accessibleName(), 'Dictionary')
        self.assertEqual(buttons[3].icon_name, 'thesaurus')
        self.assertEqual(buttons[3].accessibleName(), 'Thesaurus')
        self.assertGreater(buttons[2].y(), buttons[1].y())
        self.assertEqual(buttons[4].icon_name, 'whale')
        self.assertEqual(buttons[4].accessibleName(), 'Moby Thesaurus')
        self.assertGreater(buttons[3].y(), buttons[2].y())
        self.assertGreater(buttons[4].y(), buttons[3].y())
        self.assertEqual(buttons[5].icon_name, 'cog')
        self.assertEqual(buttons[5].accessibleName(), 'Settings')
        self.assertEqual(w.ribbon.height() - buttons[5].geometry().bottom() - 1, 10)

    def test_settings_icon_opens_tabbed_window(self):
        w = self.window
        self.assertNotIn(w.settings_menu.menuAction(), w.menuBar().actions())
        QTest.mouseClick(w.ribbon_buttons['Settings'], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        dialog = w.settings_dialog
        self.assertTrue(dialog.isVisible())
        self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
                         ['Themes', 'Appearance', 'Shortcut Keys', 'Updates', 'General'])
        w.show_settings()
        self.assertIs(w.settings_dialog, dialog)
        table = dialog.findChild(QTableWidget, 'settingsShortcuts')
        self.assertIn('Save', [table.item(i, 0).text() for i in range(table.rowCount())])
        dialog.close()
        self.assertIsNone(w.settings_dialog)

    def test_project_tree_toggles_and_switches_left_panels(self):
        w = self.window
        button = w.ribbon_buttons['Project tree']
        with patch.object(w, 'choose_file') as chooser:
            button.click()
            chooser.assert_not_called()
        self.app.processEvents()
        self.assertTrue(w.project_panel.isVisible())
        self.assertTrue(button.isChecked())
        self.assertLess(w.project_panel.mapTo(w, QPoint()).x(),
                        w.editor.mapTo(w, QPoint()).x())
        button.click()
        self.assertFalse(w.left_panels.isVisible())
        self.assertFalse(button.isChecked())
        w.ribbon_buttons['Scatchpad'].click()
        button.click()
        self.assertTrue(w.project_panel.isVisible())
        self.assertFalse(w.ribbon_buttons['Scatchpad'].isChecked())
        w.open_reference_panel('Dictionary')
        self.assertFalse(button.isChecked())
        button.click()
        w.ribbon_buttons['Scatchpad'].click()
        self.assertFalse(button.isChecked())
        self.assertTrue(w.scratchpad_panel.isVisible())
        button.click()
        w.project_panel.findChild(QToolButton).click()
        self.assertFalse(w.left_panels.isVisible())
        self.assertFalse(button.isChecked())

    def test_general_project_location_updates_tree_and_survives_restart(self):
        w = self.window
        with tempfile.TemporaryDirectory() as folder:
            nested = Path(folder) / 'chapters'
            nested.mkdir()
            note = nested / 'one.md'
            note.write_text('# One')
            w.show_settings()
            dialog = w.settings_dialog
            dialog.tabs.setCurrentIndex(4)
            with patch('settings_ui.QFileDialog.getExistingDirectory', return_value=folder):
                dialog.findChild(QPushButton, 'settingsProjectTreeBrowse').click()
            self.assertEqual(dialog.project_path.text(), folder)
            self.assertEqual(w.settings.value('project_tree_path'), folder)
            self.assertEqual(w.project_model.filePath(w.project_tree.rootIndex()), folder)
            with patch('settings_ui.QFileDialog.getExistingDirectory', return_value=''):
                dialog.choose_project_folder()
            self.assertEqual(w.project_tree_path, Path(folder))
            self.assertFalse(w.set_project_tree_path(Path(folder) / 'missing'))
            self.assertEqual(w.project_tree_path, Path(folder))
            dialog.close()
            w.close()
            w.deleteLater()
            self.app.processEvents()
            self.window = MainWindow()
            self.window.show()
            self.app.processEvents()
            self.assertEqual(self.window.project_tree_path, Path(folder))
            self.assertEqual(self.window.project_model.filePath(
                self.window.project_tree.rootIndex()), folder)

    def test_project_file_activation_respects_unsaved_changes(self):
        w = self.window
        with tempfile.TemporaryDirectory() as folder:
            note = Path(folder) / 'note.md'
            note.write_text('# Project note')
            w.set_project_tree_path(folder)
            w.ribbon_buttons['Project tree'].click()
            index = w.project_model.index(str(note))
            self.assertTrue(index.isValid())
            # Activating a directory must never try to open it as a document.
            with patch.object(w, 'open_file') as open_file:
                w.project_tree.activated.emit(w.project_tree.rootIndex())
                open_file.assert_not_called()
            w.editor.setPlainText('Unsaved writing')
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Cancel):
                w.project_tree.activated.emit(index)
            self.assertEqual(w.editor.toPlainText(), 'Unsaved writing')
            self.assertIsNone(w.current_file)
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
                w.project_tree.activated.emit(index)
            self.assertEqual(w.current_file, note)
            self.assertEqual(w.editor.toPlainText(), '# Project note')

    def test_settings_controls_apply_and_persist(self):
        w = self.window
        w.editor.setPlainText('Keep my writing')
        source = w.document_source()
        w.show_settings()
        dialog = w.settings_dialog
        dialog.font_size.setValue(20)
        dialog.spacing.setValue(12)
        dialog.page_width.setValue(800)
        dialog.heading_state.setCurrentIndex(dialog.heading_state.findData('full'))
        spelling = dialog.findChild(QCheckBox, 'settingsSpellCheck')
        spelling.setChecked(False)
        dialog.findChild(QRadioButton, 'tokyo-night').click()
        self.assertEqual(w.font_size, 20)
        self.assertEqual(w.paragraph_spacing, 12)
        self.assertEqual(w.max_page_width, 800)
        self.assertEqual(w.heading_panel_state, 'full')
        self.assertFalse(w.editor.spelling.enabled)
        self.assertEqual(w.theme_id, 'tokyo-night')
        self.assertEqual(w.document_source(), source)
        self.assertEqual(w.settings.value('font_size', type=int), 20)
        dialog.close()
        w.show_settings()
        self.assertEqual(w.settings_dialog.font_size.value(), 20)
        self.assertEqual(w.settings_dialog.spacing.value(), 12)
        self.assertEqual(w.settings_dialog.page_width.value(), 800)
        self.assertFalse(w.settings_dialog.findChild(QCheckBox, 'settingsSpellCheck').isChecked())
        w.settings_dialog.close()

    def test_settings_close_waits_for_update_worker(self):
        w = self.window
        w.show_settings()
        dialog = w.settings_dialog
        worker = Mock()
        dialog.updates.worker = worker
        worker.isRunning.return_value = True
        dialog.reject()
        self.assertTrue(dialog.isVisible())
        worker.cancelled.set.assert_called_once()
        worker.wait.assert_called_once_with(2000)
        worker.isRunning.return_value = False
        dialog.reject()
        self.assertIsNone(w.settings_dialog)

    def test_reference_icons_toggle_and_switch_left_panels(self):
        w = self.window
        for name, panel in w.reference_panels.items():
            with self.subTest(panel=name):
                button = w.ribbon_buttons[name]
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                self.app.processEvents()
                self.assertTrue(panel.isVisible())
                self.assertLess(panel.mapTo(w, QPoint()).x(), w.editor.mapTo(w, QPoint()).x())
                self.assertEqual([key for key, p in w.reference_panels.items() if p.isVisible()],
                                 [name])
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                self.assertFalse(w.left_panels.isVisible())
                self.assertTrue(w.editor.hasFocus())
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                self.assertTrue(panel.isVisible())
        w.close_left_panel()

    def test_hovering_reference_icons_does_not_open_popup_or_panel(self):
        w = self.window
        for name in w.reference_panels:
            with self.subTest(panel=name):
                QTest.mouseMove(w.ribbon_buttons[name])
                self.app.processEvents()
                self.assertIsNone(QApplication.activePopupWidget())
                self.assertFalse(w.left_panels.isVisible())

    def test_reference_icons_search_selection_only_when_opening(self):
        w = self.window
        w.editor.setPlainText('  calm\nwaters  ')
        w.editor.selectAll()
        for name, panel in w.reference_panels.items():
            with self.subTest(panel=name):
                with patch.object(w.reference_tools, 'search') as search:
                    QTest.mouseClick(w.ribbon_buttons[name], Qt.MouseButton.LeftButton)
                    self.app.processEvents()
                    search.assert_called_once_with('calm waters')
                    self.assertTrue(panel.isVisible())
                    self.assertEqual(w.editor.textCursor().selectedText(), '  calm\u2029waters  ')
                    search.reset_mock()
                    QTest.mouseClick(w.ribbon_buttons[name], Qt.MouseButton.LeftButton)
                    search.assert_not_called()
                    self.assertFalse(w.left_panels.isVisible())

    def test_reference_close_button_allows_reopening_from_icon(self):
        w = self.window
        for name, panel in w.reference_panels.items():
            with self.subTest(panel=name):
                w.ribbon_buttons[name].click()
                panel.findChild(QToolButton).click()
                self.assertFalse(w.left_panels.isVisible())
                w.ribbon_buttons[name].click()
                self.assertTrue(panel.isVisible())
                w.close_left_panel()

    def test_open_reference_without_selection_keeps_existing_search(self):
        w = self.window
        w.editor.setPlainText('calm')
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        for name, panel in w.reference_panels.items():
            with self.subTest(panel=name):
                panel.search_input.setText('previous')
                with patch.object(w.reference_tools, 'search') as search:
                    w.open_reference_panel(name)
                    search.assert_not_called()
                self.assertEqual(panel.search_input.text(), 'previous')

    def test_open_reference_ignores_whitespace_selection(self):
        w = self.window
        w.editor.setPlainText(' \n ')
        w.editor.selectAll()
        with patch.object(w.reference_tools, 'search') as search:
            w.open_reference_panel('Dictionary')
            search.assert_not_called()

    def hover_character(self, offset, fraction=0.5):
        editor = self.window.editor
        self.app.processEvents()
        cursor = QTextCursor(editor.document())
        cursor.setPosition(offset)
        rect = editor.cursorRect(cursor)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
        end = editor.cursorRect(cursor)
        position = QPoint(int(rect.left() + (end.left() - rect.left()) * fraction),
                          rect.center().y())
        QTest.mouseMove(editor.viewport(), position)
        self.app.processEvents()

    def test_ctrl_l_searches_hovered_word_and_preserves_selection(self):
        w = self.window
        w.editor.setPlainText('Selected text, peaceful waters.')
        w.editor.selectAll()
        original = w.editor.textCursor()
        for offset, fraction in ((15, 0.2), (19, 0.8), (22, 0.8)):
            with self.subTest(offset=offset):
                w.close_left_panel()
                self.hover_character(offset, fraction)
                with patch.object(w.reference_tools, 'search') as search:
                    QTest.keyClick(w.editor, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
                    self.app.processEvents()
                    search.assert_called_once_with('peaceful')
                self.assertTrue(w.reference_panels['Dictionary'].isVisible())
                self.assertEqual(w.editor.textCursor().position(), original.position())
                self.assertEqual(w.editor.textCursor().anchor(), original.anchor())
                self.assertEqual(w.editor.toPlainText(), 'Selected text, peaceful waters.')

    def test_ctrl_l_ignores_whitespace_punctuation_and_outside_document(self):
        w = self.window
        w.editor.setPlainText('calm, waters')
        w.editor.setFocus()
        for offset in (4, 5):
            with self.subTest(offset=offset):
                self.hover_character(offset)
                with patch.object(w.reference_tools, 'search') as search:
                    QTest.keyClick(w.editor, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
                    search.assert_not_called()
                self.assertFalse(w.left_panels.isVisible())
        viewport = w.editor.viewport()
        for position in (QPoint(viewport.width() - 5, 5),
                         QPoint(100, viewport.height() - 10)):
            QTest.mouseMove(viewport, position)
            with patch.object(w.reference_tools, 'search') as search:
                QTest.keyClick(w.editor, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
                search.assert_not_called()
        QTest.mouseMove(w.ribbon_buttons['Scatchpad'])
        with patch.object(w.reference_tools, 'search') as search:
            QTest.keyClick(w.editor, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
            search.assert_not_called()

    def test_ctrl_l_resolves_word_after_scrolling(self):
        w = self.window
        w.editor.setPlainText('earlier lines\n' * 100 + 'peaceful waters')
        w.editor.moveCursor(QTextCursor.MoveOperation.End)
        w.editor.ensureCursorVisible()
        self.app.processEvents()
        self.assertGreater(w.editor.verticalScrollBar().value(), 0)
        self.hover_character(len('earlier lines\n' * 100) + 3)
        with patch.object(w.reference_tools, 'search') as search:
            QTest.keyClick(w.editor, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
            search.assert_called_once_with('peaceful')

    def test_switching_reference_and_scratchpad_preserves_notes(self):
        w = self.window
        w.ribbon_buttons['Scatchpad'].click()
        w.scratchpad_editor.setPlainText('Keep these notes')
        source = w.document_source()
        w.open_reference_panel('Dictionary')
        self.assertFalse(w.scratchpad_panel.isVisible())
        self.assertFalse(w.ribbon_buttons['Scatchpad'].isChecked())
        w.ribbon_buttons['Scatchpad'].click()
        self.assertTrue(w.scratchpad_panel.isVisible())
        self.assertFalse(w.reference_panels['Dictionary'].isVisible())
        self.assertEqual(w.scratchpad_editor.toPlainText(), 'Keep these notes')
        self.assertEqual(w.document_source(), source)
        w.scratchpad_editor.clear()

    def reveal_ribbon(self):
        QTest.mouseMove(self.window.ribbon_reveal, QPoint(3, 100))
        self.app.processEvents()
        self.assertTrue(self.window.ribbon.isVisible())
        self.finish_ribbon_animation()

    def finish_ribbon_animation(self):
        animation = self.window.ribbon_animation
        animation.setCurrentTime(animation.duration())

    def test_auto_hide_reveal_leave_and_pin(self):
        w = self.window
        w.ribbon_auto_hide_action.trigger()
        self.finish_ribbon_animation()
        self.assertFalse(w.ribbon.isVisible())
        self.assertEqual(w.ribbon_hide_timer.interval(), w.heading_panel_hide_timer.interval())
        self.assertEqual(w.ribbon_animation.duration(), w.heading_panel_animation.duration())
        self.assertEqual(w.ribbon_animation.easingCurve(), w.heading_panel_animation.easingCurve())
        self.reveal_ribbon()
        self.assertEqual(w.ribbon_animation.duration(), 300)
        QTest.mouseMove(w.ribbon_buttons['Scatchpad'])
        self.assertFalse(w.ribbon_hide_timer.isActive())
        QTest.mouseMove(w.editor.viewport(), QPoint(200, 150))
        self.assertTrue(w.ribbon_hide_timer.isActive())
        # Returning before the delay expires cancels the pending hide.
        QTest.mouseMove(w.ribbon_buttons['Scatchpad'])
        self.assertFalse(w.ribbon_hide_timer.isActive())
        QTest.mouseMove(w.editor.viewport(), QPoint(200, 150))
        QTest.qWait(w.ribbon_hide_timer.interval() + 100)
        self.assertEqual(w.ribbon_animation.state(), QAbstractAnimation.State.Running)
        self.finish_ribbon_animation()
        self.assertFalse(w.ribbon.isVisible())
        w.ribbon_auto_hide_action.trigger()
        self.finish_ribbon_animation()
        self.assertTrue(w.ribbon.isVisible())
        self.assertFalse(w.ribbon_reveal.isVisible())
        self.assertFalse(w.ribbon_hide_timer.isActive())

    def test_slide_and_return_during_close(self):
        w = self.window
        w.ribbon_auto_hide_action.trigger()
        self.finish_ribbon_animation()
        self.assertEqual(w.ribbon.width(), 0)
        QTest.mouseMove(w.ribbon_reveal, QPoint(3, 100))
        animation = w.ribbon_animation
        animation.setCurrentTime(animation.duration() // 2)
        self.assertGreater(w.ribbon.width(), 0)
        self.assertLess(w.ribbon.width(), w.ribbon_expanded_width)
        self.finish_ribbon_animation()
        self.assertEqual(w.ribbon.width(), w.ribbon_expanded_width)

        QTest.mouseMove(w.editor.viewport(), QPoint(200, 150))
        w.hide_ribbon_after_delay()
        self.assertEqual(animation.duration(), 750)
        animation.setCurrentTime(animation.duration() // 2)
        closing_width = w.ribbon.width()
        self.assertGreater(closing_width, 0)
        self.assertLess(closing_width, w.ribbon_expanded_width)
        QTest.mouseMove(w.ribbon_reveal, QPoint(3, 100))
        self.assertTrue(w._ribbon_target_visible)
        self.assertEqual(animation.duration(), 300)
        self.assertEqual(w.ribbon.width(), closing_width)
        self.assertFalse(w.ribbon_hide_timer.isActive())
        self.finish_ribbon_animation()
        self.assertTrue(w.ribbon.isVisible())
        self.assertEqual(w.ribbon.width(), w.ribbon_expanded_width)

    def test_preference_survives_reopening_and_heading_setting(self):
        w = self.window
        w.ribbon_auto_hide_action.trigger()
        w.set_heading_panel_auto_hide(True)
        w.set_heading_panel_auto_hide(False)
        self.assertTrue(w.testAttribute(Qt.WidgetAttribute.WA_Hover))
        w.close()
        w.deleteLater()
        self.app.processEvents()
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.window.ribbon_auto_hide_action.isChecked())
        self.assertFalse(self.window.ribbon.isVisible())
        self.reveal_ribbon()
        self.window.set_heading_panel_auto_hide(True)
        self.window.ribbon_auto_hide_action.trigger()
        self.assertTrue(self.window.testAttribute(Qt.WidgetAttribute.WA_Hover))
