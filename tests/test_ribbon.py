"""Toolbar ribbon and persisted auto-hide behavior."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest

from PySide6.QtCore import QAbstractAnimation, QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

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

    def test_ribbon_is_left_and_shows_only_scatchpad(self):
        w = self.window
        self.assertTrue(w.ribbon.isVisible())
        self.assertLess(w.ribbon.mapTo(w, QPoint()).x(), w.editor.mapTo(w, QPoint()).x())
        buttons = w.ribbon.findChildren(QToolButton)
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].icon_name, 'notepad')
        self.assertEqual(buttons[0].accessibleName(), 'Scatchpad')

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
