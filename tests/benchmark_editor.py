"""Repeatable editor microbenchmarks; run from the repository root.

QT_QPA_PLATFORM=offscreen python3 tests/benchmark_editor.py --output /tmp/write.json
Times are median milliseconds per operation (five samples after warmup).
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from main import MainWindow


def measure(operation, iterations=30):
    operation()
    samples = []
    for _ in range(5):
        start = perf_counter()
        for _ in range(iterations):
            operation()
        samples.append((perf_counter() - start) * 1000 / iterations)
    return round(statistics.median(samples), 4)


def run():
    app = QApplication.instance() or QApplication([])
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        settings = QSettings(str(Path(directory) / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', directory)
        settings.setValue('spell_check', False)
        with patch('main.QSettings', return_value=settings):
            window = MainWindow()
        window.resize(1120, 760)
        window.show()
        editor = window.editor
        for paragraphs in (500, 5000):
            path = Path(directory) / 'prose.md'
            path.write_text(('One two three four five six seven eight nine ten eleven twelve.\n' * paragraphs))
            window.open_file(path)
            app.processEvents()
            prefix = f'prose_{paragraphs}'
            results[prefix + '_status_ms'] = measure(window.update_status)
            results[prefix + '_clean_query_ms'] = measure(window.has_unsaved_changes)
            editor.moveCursor(QTextCursor.MoveOperation.End)
            editor.insertPlainText('x')
            results[prefix + '_dirty_query_ms'] = measure(window.has_unsaved_changes)

            def type_character():
                editor.insertPlainText('x')
                app.processEvents()

            results[prefix + '_typing_ms'] = measure(type_character, 10)
            window._saved_text = window.document_source()
        path = Path(directory) / 'table.md'
        path.write_text('| Name | Description | Status | Price |\n| --- | --- | :---: | ---: |\n' +
                        ''.join(f'| Item {i} | **Some text** and `code` | Active | $10 |\n' for i in range(120)) + 'After')
        window.open_file(path)
        # This benchmark measures a complete eager table rebuild. File loading's
        # progressive rendering is measured by benchmark_file_switching.py.
        editor._defer_tables = False
        editor.update_code_panels(full=True)
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.verticalScrollBar().setValue(0)
        app.processEvents()
        results['table_repaint_ms'] = measure(lambda: editor.viewport().repaint())

        def rebuild_table():
            editor.update_code_panels(full=True)
            editor.viewport().repaint()

        results['table_rebuild_and_paint_ms'] = measure(rebuild_table, 5)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
