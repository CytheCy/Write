"""Recursive search, async panel updates, and result navigation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from threading import Event
import tempfile
import unittest

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow
from project_search import search_project


class ProjectSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                          cls.settings_dir.name)
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        QThreadPool.globalInstance().waitForDone()
        cls.settings_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'nested').mkdir()
        self.a = self.root / 'a.md'
        self.b = self.root / 'nested' / 'b.txt'
        self.a.write_text('😀 Trinidad and TRINIDAD\n<Trinidad>')
        self.b.write_text('Other line\r\nTrinidad again')
        (self.root / 'binary').write_bytes(b'\x00Trinidad')
        (self.root / 'invalid').write_bytes(b'\xffTrinidad')
        (self.root / 'link').symlink_to(self.a)
        QSettings('Write', 'Write').clear()
        QSettings('Write', 'Write').setValue('project_tree_path', str(self.root))
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._updating = True
        self.window.close()
        QThreadPool.globalInstance().waitForDone()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_results(self, count):
        panel = self.window.project_search
        for _ in range(150):
            if panel.count.text() == f'{count} results':
                return
            QTest.qWait(20)
        self.fail(f'Search did not finish: {panel.count.text()}')

    def test_recursive_literal_search_limits_and_cancellation(self):
        matches, limited, errors = search_project(self.root, 'Trinidad', Event())
        self.assertEqual(len(matches), 4)
        self.assertEqual({m.path for m in matches}, {self.a, self.b})
        self.assertFalse(limited)
        self.assertEqual(errors, [])
        for match in matches:
            source = match.path.read_text()
            self.assertEqual(source[match.start:match.end].lower(), 'trinidad')
            self.assertEqual(match.excerpt[match.highlight_start:match.highlight_end].lower(),
                             'trinidad')
        self.assertEqual(search_project(self.root, '<Trinidad>', Event())[0][0].path, self.a)
        self.assertTrue(search_project(self.root, 'Trinidad', Event(), limit=2)[1])
        cancelled = Event()
        cancelled.set()
        self.assertEqual(search_project(self.root, 'Trinidad', cancelled)[0], [])

    def test_ribbon_panel_groups_sort_navigation_and_clear(self):
        w = self.window
        button = w.ribbon_buttons['Search project']
        self.assertGreater(button.y(), w.ribbon_buttons['Project tree'].y())
        self.assertLess(button.y(), w.ribbon_buttons['Scatchpad'].y())
        button.click()
        panel = w.project_search
        self.assertTrue(panel.isVisible())
        self.assertTrue(button.isChecked())
        panel.input.setText('Trinidad')
        self.wait_results(4)
        self.assertEqual(panel.results.topLevelItemCount(), 2)
        first = panel.results.topLevelItem(0)
        self.assertEqual(first.childCount(), 3)
        panel.activate(first.child(1), 0)
        self.assertEqual(w.current_file, self.a)
        self.assertEqual(w.editor.textCursor().selectedText(), 'TRINIDAD')
        self.assertFalse(w.editor.document().isModified())
        panel.sort.setCurrentIndex(1)
        self.assertIn('b', panel.results.topLevelItem(0).text(0))
        panel.input.clear()
        self.assertEqual(panel.results.topLevelItemCount(), 0)
        self.assertEqual(panel.count.text(), 'Enter text to search')
        w.ribbon_buttons['Project tree'].click()
        self.assertFalse(button.isChecked())
        self.assertTrue(w.project_panel.isVisible())
        button.click()
        w.close_left_panel()
        self.assertFalse(button.isChecked())

    def test_unsaved_open_documents_and_root_change_invalidate_results(self):
        w = self.window
        w.open_file(self.a)
        w.editor.setPlainText('unsaved needle')
        w.open_file(self.b)
        w.editor.setPlainText('another needle')
        w.toggle_project_search()
        panel = w.project_search
        panel.input.setText('needle')
        self.wait_results(2)
        panel.activate(panel.results.topLevelItem(0).child(0), 0)
        self.assertEqual(w.editor.toPlainText(), 'unsaved needle')
        self.assertEqual(w.editor.textCursor().selectedText(), 'needle')
        self.assertTrue(w.editor.document().isModified())
        generation = panel.generation
        w.set_project_tree_path(self.root / 'nested')
        panel.finished(generation, ([], False, []))
        for _ in range(150):
            if panel.count.text() == '1 result':
                break
            QTest.qWait(20)
        self.assertEqual(panel.count.text(), '1 result')
        self.assertEqual(panel.matches[0].path, self.b)

    def test_navigation_accounts_for_scratch_blocks_and_unicode(self):
        self.a.write_text('😀 intro\n---\nscratch:needle scratch\n---\nneedle body')
        w = self.window
        w.toggle_project_search()
        panel = w.project_search
        panel.input.setText('needle')
        self.wait_results(2)
        group = panel.results.topLevelItem(0)
        panel.activate(group.child(1), 0)
        self.assertEqual(w.editor.textCursor().selectedText(), 'needle')
        self.assertEqual(w.editor.textCursor().position(), 15)
        panel.activate(group.child(0), 0)
        self.assertTrue(w.scratchpad_panel.isVisible())
        self.assertEqual(w.scratchpad_editor.textCursor().selectedText(), 'needle')


if __name__ == '__main__':
    unittest.main()
