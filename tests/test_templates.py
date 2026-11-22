"""Project templates insert plain text into the active document with undo."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QListWidget

from main import MainWindow


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', str(self.root))
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow()
        self.templates = self.root / '.app' / 'templates'

    def tearDown(self):
        self.window._updating = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def write_template(self, name, text):
        self.templates.mkdir(parents=True, exist_ok=True)
        path = self.templates / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_menu_lists_only_files_and_inserts_selection_with_single_undo(self):
        source = '# Meeting 😀\n**Agenda**\n'
        self.write_template('z.txt', 'Other')
        path = self.write_template('Agenda.md', source)
        (self.templates / 'folder').mkdir()
        editor = self.window.editor
        editor.setPlainText('Before replace after')
        editor.setTextCursor(editor.document().find('replace'))

        def choose(dialog):
            items = dialog.findChild(QListWidget)
            self.assertEqual([items.item(i).text() for i in range(items.count())],
                             ['Agenda.md', 'z.txt'])
            return QDialog.DialogCode.Accepted

        action = next(a for a in self.window.tools_menu.actions() if a.text() == 'Insert Template')
        with patch.object(QDialog, 'exec', choose):
            action.trigger()
        self.assertEqual(editor.toPlainText(), 'Before ' + source + ' after')
        self.assertTrue(self.window.has_unsaved_changes())
        self.assertEqual(path.read_text(encoding='utf-8'), source)
        editor.undo()
        self.assertEqual(editor.toPlainText(), 'Before replace after')

    def test_cancel_and_missing_or_empty_folder_leave_document_unchanged(self):
        self.window.editor.setPlainText('Draft')

        def empty(dialog):
            self.assertEqual(dialog.findChild(QListWidget).count(), 0)
            buttons = dialog.findChild(QDialogButtonBox)
            self.assertFalse(buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
            return QDialog.DialogCode.Rejected

        with patch.object(QDialog, 'exec', empty):
            self.window.insert_template()
            self.templates.mkdir()
            self.window.insert_template()
        self.write_template('note.txt', 'Template')
        with patch.object(QDialog, 'exec', return_value=QDialog.DialogCode.Rejected):
            self.window.insert_template()
        self.assertEqual(self.window.editor.toPlainText(), 'Draft')

    def test_inserts_into_active_tab_at_cursor(self):
        first = self.root / 'first.md'
        second = self.root / 'second.md'
        first.write_text('First')
        second.write_text('Second')
        self.window.open_file(first)
        self.window.open_file(second)
        self.window.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.write_template('note.txt', '\nTemplate')
        with patch.object(QDialog, 'exec', return_value=QDialog.DialogCode.Accepted):
            self.window.insert_template()
        self.assertEqual(self.window.editor.toPlainText(), 'Second\nTemplate')
        self.window.activate_tab(0)
        self.assertEqual(self.window.editor.toPlainText(), 'First')

    def test_activating_another_filename_accepts_the_picker(self):
        self.write_template('a.txt', 'First template')
        self.write_template('b.txt', 'Chosen template')

        def activate():
            dialog = QApplication.activeModalWidget()
            items = dialog.findChild(QListWidget)
            items.setCurrentRow(1)
            items.itemActivated.emit(items.currentItem())

        QTimer.singleShot(0, activate)
        self.window.insert_template()
        self.assertEqual(self.window.editor.toPlainText(), 'Chosen template')

    def test_unreadable_or_invalid_template_reports_error_without_editing(self):
        path = self.write_template('broken.txt', 'Template')
        self.window.editor.setPlainText('Draft')
        for failure in ('deleted', 'invalid'):
            def choose(dialog):
                if failure == 'deleted':
                    path.unlink()
                else:
                    path.write_bytes(b'\xff')
                return QDialog.DialogCode.Accepted

            with patch.object(QDialog, 'exec', choose), patch('main.QMessageBox.warning') as warning:
                self.window.insert_template()
            warning.assert_called_once()
            self.assertEqual(self.window.editor.toPlainText(), 'Draft')
            path.write_text('Template')


if __name__ == '__main__':
    unittest.main()
