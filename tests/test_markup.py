"""Markup persistence, hover controls, coloring and undoable replacements."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QToolButton
from main import MainWindow
from markup import Category, CategoryDialog, category_matches, read_category
from project_colors import PALETTE


class MarkupTests(unittest.TestCase):
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
        self.window.show()
        self.app.processEvents()
        self.controller = self.window.markup
        self.path = self.root / '.app/markup/Story Specific.txt'
        self.path.write_text('woman|fem\nWoman|Fem\n')
        self.controller.reload()

    def tearDown(self):
        self.controller.menu.close()
        if self.controller.dialog:
            self.controller.dialog.reject()
        self.window._updating = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def colored_ranges(self, color=None):
        """Inspect the rendered foreground ranges rather than editor cursors."""
        color = color or read_category(self.path).color
        editor = self.window.editor
        selections = []
        block = editor.document().firstBlock()
        while block.isValid():
            for item in block.layout().formats():
                if (item.format.foreground().style() == Qt.BrushStyle.NoBrush
                        or item.format.foreground().color().name() != color):
                    continue
                selection = SimpleNamespace(cursor=QTextCursor(block),
                                            format=QTextCharFormat(item.format))
                selection.cursor.setPosition(block.position() + item.start)
                selection.cursor.setPosition(block.position() + item.start + item.length,
                                             QTextCursor.MoveMode.KeepAnchor)
                selections.append(selection)
            block = block.next()
        return selections

    def test_hover_toggle_and_project_change(self):
        w = self.window
        QApplication.sendEvent(w.ribbon_buttons['Markup'], QEvent(QEvent.Type.Enter))
        self.assertTrue(self.controller.menu.isVisible())
        checks = self.controller.menu.findChildren(QCheckBox)
        self.assertEqual([c.text() for c in checks], ['Story Specific'])
        w.editor.setPlainText('woman')
        self.controller.refresh()
        self.assertEqual(len(self.colored_ranges()), 1)
        checks[0].click()
        self.assertFalse(self.colored_ranges())
        self.assertFalse(self.controller.enabled(self.controller.categories[0]))
        self.controller.reload()
        self.assertFalse(self.colored_ranges())
        QTest.mouseMove(w.editor.viewport(), QPoint(150, 80))
        QApplication.sendEvent(self.controller.menu, QEvent(QEvent.Type.Leave))
        QTest.qWait(300)
        self.assertFalse(self.controller.menu.isVisible())
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(w.set_project_tree_path(folder))
            self.assertTrue((Path(folder) / '.app/markup').is_dir())
            self.assertFalse(self.controller.categories)

    def test_color_only_utf16_replacement_undo_and_source_unchanged(self):
        w = self.window
        self.path.write_text('# color: #528fdf\nwoman|fem\n')
        self.controller.reload()
        source = '😀 woman Woman womanhood'
        w.editor.setPlainText(source)
        self.controller.refresh()
        self.assertEqual(w.editor.toPlainText(), source)
        selections = self.colored_ranges()
        self.assertEqual([s.cursor.selectedText() for s in selections], ['woman', 'Woman'])
        self.assertEqual(selections[0].cursor.selectionStart(), 3)
        self.assertEqual(selections[0].format.foreground().color().name(), '#528fdf')
        self.assertEqual(selections[0].format.background().style(), Qt.BrushStyle.NoBrush)
        cursor = QTextCursor(selections[0].cursor)
        cursor.setPosition(cursor.selectionEnd())
        # The right half of the final glyph resolves to an insertion point
        # after the word; it must still count as a click on colored text.
        point = w.editor.cursorRect(cursor).center() - QPoint(2, 0)
        QTest.mouseClick(w.editor.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier, point)
        self.assertEqual(w.editor.toPlainText(), '😀 fem Woman womanhood')
        w.editor.undo()
        self.assertEqual(w.editor.toPlainText(), source)
        w.editor.redo()
        self.assertEqual(w.editor.toPlainText(), '😀 fem Woman womanhood')
        self.controller.refresh()
        capitalized = self.colored_ranges()[0].cursor
        capitalized.setPosition(capitalized.selectionStart() + 2)
        QTest.mouseClick(w.editor.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier,
                         w.editor.cursorRect(capitalized).center())
        self.assertEqual(w.editor.toPlainText(), '😀 fem Fem womanhood')
        w.editor.undo()
        self.assertEqual(w.editor.toPlainText(), '😀 fem Woman womanhood')
        w.new_file()
        self.controller.refresh()
        self.assertFalse(self.colored_ranges())

    def test_colors_update_immediately_while_typing(self):
        editor = self.window.editor
        editor.setPlainText('woman ')

        editor.moveCursor(QTextCursor.MoveOperation.Start)
        editor.insertPlainText('A ')
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()], ['woman'])
        self.assertEqual(self.colored_ranges()[0].cursor.selectionStart(), 2)

        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.insertPlainText('Woman')
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()],
                         ['woman', 'Woman'])

    def test_edited_word_is_rechecked_before_ctrl_click(self):
        editor = self.window.editor
        editor.setPlainText('woman ')
        cursor = QTextCursor(editor.document())
        cursor.setPosition(2)
        cursor.insertText('x')
        self.assertFalse(self.colored_ranges())

        cursor.setPosition(1)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier,
                         editor.cursorRect(cursor).center())
        self.assertEqual(editor.toPlainText(), 'woxman ')
        self.assertFalse(self.colored_ranges())

    def test_phrase_colors_follow_paragraph_splits_joins_and_undo(self):
        self.path.write_text('woman friend|pal\n')
        self.controller.reload()
        editor = self.window.editor
        editor.setPlainText('woman friend\nWoman friend')
        cursor = QTextCursor(editor.document())
        cursor.setPosition(5)
        editor.setTextCursor(cursor)
        editor.insertPlainText('\n')
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()], ['Woman friend'])
        editor.undo()
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()],
                         ['woman friend', 'Woman friend'])
        editor.redo()
        cursor.setPosition(5)
        cursor.deleteChar()
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()],
                         ['woman friend', 'Woman friend'])
        cursor.setPosition(8)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier,
                         editor.cursorRect(cursor).center())
        self.assertEqual(editor.toPlainText(), 'pal\nWoman friend')

    def test_document_switch_uses_current_document_colors(self):
        editor = self.window.editor
        editor.setPlainText('woman ')
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.insertPlainText('changed')
        index = self.window._active_tab
        self.window.new_file()
        self.assertFalse(self.colored_ranges())
        self.window.activate_tab(index)
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()], ['woman'])

    def test_edits_highlight_only_changed_paragraph_and_reuse_rules(self):
        editor = self.window.editor
        editor.setPlainText('woman friend\n' * 300)
        cursor = QTextCursor(editor.document().findBlockByNumber(150))
        cursor.setPosition(cursor.position() + 6)
        editor.setTextCursor(cursor)
        matcher = self.controller.matcher
        with patch.object(self.controller, 'highlight_block',
                          wraps=self.controller.highlight_block) as highlight, \
                patch.object(self.controller, 'refresh', side_effect=AssertionError('full refresh')):
            editor.insertPlainText('dear ')
            self.app.processEvents()
        self.assertGreater(highlight.call_count, 0)
        self.assertLessEqual(highlight.call_count, 2)
        self.assertTrue(all(call.args[1] == 'woman dear friend' for call in highlight.call_args_list))
        self.assertIs(self.controller.matcher, matcher)
        self.controller.reload()
        self.assertIs(self.controller.matcher, matcher)

    def test_markup_preserves_markdown_styles_and_works_in_plain_text_mode(self):
        editor = self.window.editor
        editor.setPlainText('**woman** and *Woman*\nBody')
        editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        ranges = self.colored_ranges()
        self.assertEqual([s.cursor.selectedText() for s in ranges], ['woman', 'Woman'])
        self.assertEqual(ranges[0].format.fontWeight(), QFont.Weight.Bold)
        self.assertTrue(ranges[1].format.fontItalic())
        self.window.highlighter.enabled = False
        self.window.highlighter.rehighlight()
        self.assertEqual([s.cursor.selectedText() for s in self.colored_ranges()], ['woman', 'Woman'])

    def test_category_refresh_does_not_modify_source_or_undo_history(self):
        editor = self.window.editor
        editor.setPlainText('woman')
        editor.insertPlainText('A ')
        document = editor.document()
        document.setModified(False)
        undo_steps = document.availableUndoSteps()
        self.path.write_text('# color: #528fdf\nwoman|fem\n')
        self.controller.reload()
        self.assertEqual(editor.toPlainText(), 'A woman')
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), undo_steps)
        self.assertEqual(len(self.colored_ranges('#528fdf')), 1)

    def test_dialog_save_edit_rename_and_validation(self):
        dialog = CategoryDialog(self.path.parent, parent=self.window)
        dialog.name_input.setText('New category')
        dialog.swatches[5].click()
        self.assertEqual(len(dialog.swatches), len(PALETTE))
        dialog.rules.item(0, 0).setText('a phrase')
        dialog.rules.item(0, 1).setText('replacement')
        dialog.save()
        category = read_category(dialog.saved_path)
        self.assertEqual(category.color, PALETTE[5][1])
        self.assertEqual(category.rules, [('a phrase', 'replacement')])
        edit = CategoryDialog(self.path.parent, category, self.window)
        edit.name_input.setText('Story Specific')
        edit.save()
        self.assertIn('already exists', edit.error.text())
        self.assertEqual(self.path.read_text(), 'woman|fem\nWoman|Fem\n')
        edit.name_input.setText('../escape')
        edit.save()
        self.assertIsNone(edit.saved_path)
        edit.name_input.setText('Renamed')
        edit.rules.item(0, 1).setText('')
        edit.save()
        self.assertFalse(category.path.exists())
        self.assertEqual(read_category(edit.saved_path).rules, [('a phrase', '')])
        dialog.deleteLater()
        edit.deleteLater()

    def test_literal_phrase_and_word_boundaries(self):
        category = Category(self.path, '#528fdf', [('woman', 'fem'), ('woman friend', 'pal'), ('a.b', 'dot')])
        text = 'womanhood woman friend Woman a.b axb'
        self.assertEqual([(text[a:b], replacement) for a, b, replacement, _ in category_matches(text, [category])],
                         [('woman friend', 'pal'), ('Woman', 'Fem'), ('a.b', 'dot')])

    def test_popup_add_edit_and_cancel(self):
        self.controller.show_popup()
        self.controller.menu.actions()[-1].trigger()
        dialog = self.controller.dialog
        self.assertTrue(dialog.isVisible())
        dialog.name_input.setText('New')
        dialog.rules.item(0, 0).setText('girl')
        dialog.rules.item(0, 1).setText('person')
        dialog.save()
        self.assertIsNone(self.controller.dialog)
        self.assertEqual([c.name for c in self.controller.categories], ['New', 'Story Specific'])
        self.controller.show_popup()
        edit = next(b for b in self.controller.menu.findChildren(QToolButton)
                    if b.accessibleName() == 'Edit New')
        edit.click()
        self.assertEqual(self.controller.dialog.name_input.text(), 'New')
        self.controller.dialog.name_input.setText('Uncommitted')
        self.controller.dialog.reject()
        self.assertFalse((self.path.parent / 'Uncommitted.txt').exists())
        self.assertTrue((self.path.parent / 'New.txt').exists())

    def test_external_file_change_updates_colors(self):
        self.window.editor.setPlainText('woman girl')
        self.path.write_text('# color: #e05252\ngirl|person\n')
        QTest.qWait(300)
        self.app.processEvents()
        selections = self.colored_ranges()
        self.assertEqual([s.cursor.selectedText() for s in selections], ['girl'])
        self.assertEqual(selections[0].format.foreground().color().name(), '#e05252')


class MarkupMatchingTests(unittest.TestCase):
    def matches(self, text, rules):
        category = Category(Path('Example.txt'), '#528fdf', rules)
        return [(text[start:end], replacement)
                for start, end, replacement, _ in category_matches(text, [category])]

    def test_initial_case_for_words_and_phrases_preserves_replacement_case(self):
        self.assertEqual(self.matches('woman Woman woman friend Woman friend WOMAN',
                                     [('woman', 'fem'), ('woman friend', 'myFriend')]),
                         [('woman', 'fem'), ('Woman', 'Fem'),
                          ('woman friend', 'myFriend'), ('Woman friend', 'MyFriend')])

    def test_explicit_capitalized_rule_and_empty_replacement(self):
        self.assertEqual(self.matches('woman Woman Remove remove',
                                     [('woman', 'fem'), ('Woman', 'person'), ('remove', '')]),
                         [('woman', 'fem'), ('Woman', 'Person'), ('Remove', ''), ('remove', '')])

    def test_capitalized_watch_also_matches_lowercase_initial(self):
        self.assertEqual(self.matches('Élan élan éLAN', [('Élan', 'poise')]),
                         [('Élan', 'Poise'), ('élan', 'poise')])


if __name__ == '__main__':
    unittest.main()
