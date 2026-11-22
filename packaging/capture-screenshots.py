#!/usr/bin/env python3
"""Refresh theme examples from Write using an isolated, offscreen Qt session."""

import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QTimer
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from main import APP_NAME, FILE_FILTER, MainWindow
from themes import THEMES


SAMPLE = """# The forest after rain
The house stood where the road ended, beneath a canopy of old trees. Mara paused at the gate and listened. Somewhere beyond the garden, water was running.
## Chapter one
*There is still time*, she thought. She had written those words in her notebook that morning, before the letter arrived.
> A quiet place to write.
- Gather your thoughts
- Find the next sentence
1. Begin with a small detail
2. Follow where it leads
She opened [her notes](https://example.com) and began again.
```
Rain on leaves. A light in the window.
```
"""


def capture(widget, name):
    widget.show()
    QApplication.processEvents()
    image = widget.grab().toImage()
    image.setText("Application", APP_NAME)
    assert image.save(str(ROOT / "artifacts" / name)), name


def main():
    assert APP_NAME == "Write", "Run after the Write identity is configured"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="write-screenshots-") as settings_dir:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for fmt in (QSettings.Format.IniFormat, QSettings.Format.NativeFormat):
            QSettings.setPath(fmt, QSettings.Scope.UserScope, settings_dir)
        app = QApplication([])
        app.setApplicationName(APP_NAME)
        app.setDesktopFileName("write.desktop")
        app.setWindowIcon(QIcon(str(ROOT / "write.svg")))
        app.setStyle("Fusion")
        for theme in THEMES:
            QSettings("Write", "Write").clear()
            QSettings("Write", "Write").setValue("project_tree_path", settings_dir)
            window = MainWindow()
            window.resize(1120, 850)
            window.set_theme(theme)
            window.editor.setPlainText(SAMPLE)
            window.editor.moveCursor(QTextCursor.MoveOperation.Start)
            window._saved_text = SAMPLE
            window.update_title()
            capture(window, f"{theme}.png")

            appearance = window.create_appearance_dialog()
            capture(appearance, f"{theme}-appearance.png")
            appearance.close()
            appearance.deleteLater()

            file_dialog = QFileDialog(window, "Open note", str(ROOT), FILE_FILTER)
            file_dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            file_dialog.resize(760, 480)
            capture(file_dialog, f"{theme}-file-dialog.png")
            file_dialog.close()
            file_dialog.deleteLater()

            # Capture the application's actual unsaved-changes prompt.
            window._saved_text = ""

            def capture_prompt():
                prompt = app.activeModalWidget()
                assert isinstance(prompt, QMessageBox)
                capture(prompt, f"{theme}-message.png")
                prompt.done(QMessageBox.StandardButton.Cancel)

            QTimer.singleShot(50, capture_prompt)
            window.confirm_discard()
            window._saved_text = SAMPLE
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    main()
