"""Measure tree activation through first paint and completion of load work.

QT_QPA_PLATFORM=offscreen python3 tests/benchmark_file_switching.py --output /tmp/switch.json
Use --root to measure another source checkout with the same fixtures and harness.
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


def run(root, samples):
    sys.path.insert(0, str(root))
    from PySide6.QtCore import QCoreApplication, QEvent, QSettings
    from PySide6.QtWidgets import QApplication
    from main import MainWindow, NoteEditor

    app = QApplication.instance() or QApplication([])
    painted = []
    original_paint = NoteEditor.paintEvent

    def paint(editor, event):
        original_paint(editor, event)
        if editor is window.editor:
            painted.append(perf_counter())

    def pending():
        timers = [window.editor._code_update_timer]
        for owner, name in ((window, '_load_details_timer'),
                            (window.editor, '_table_prepare_timer'),
                            (window.editor, '_highlight_timer')):
            timer = getattr(owner, name, None)
            if timer is not None:
                timers.append(timer)
        return any(timer.isActive() for timer in timers)

    def settle(require_paint=False):
        deadline = perf_counter() + 30
        idle = 0
        while idle < 3 or (require_paint and not painted):
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            idle = 0 if pending() else idle + 1
            if perf_counter() > deadline:
                raise RuntimeError('File load did not settle')

    prose = 'One two three four five six seven eight nine ten eleven twelve.\n'
    fixtures = {f'prose_{n}': prose * n for n in (100, 500, 5000)}
    fixtures['table_120'] = ('| Name | Description | Status | Price |\n'
                             '| --- | --- | :---: | ---: |\n' + ''.join(
        f'| Item {i} | **Some text** and `code` | Active | $10 |\n' for i in range(120)))
    fixtures['mixed_500'] = ''.join(
        f'## Section {i}\n{prose * 4}```python\nx = 1\n```\n' for i in range(100))
    fixtures['find_5000'] = prose * 5000
    results = {}
    with tempfile.TemporaryDirectory(prefix='write-switch-') as directory:
        directory = Path(directory)
        settings = QSettings(str(directory / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('spell_check', False)
        settings.setValue('project_tree_path', str(directory))
        for name, source in fixtures.items():
            (directory / (name + '.md')).write_text(source)
        anchor = directory / 'anchor.md'
        anchor.write_text('Anchor note\n')
        NoteEditor.paintEvent = paint
        with patch('main.QSettings', return_value=settings):
            window = MainWindow(anchor)
        window.resize(1120, 760)
        window.show()
        window.toggle_project_tree()
        settle()
        with patch.object(NoteEditor, 'paintEvent', paint):
            for name, source in fixtures.items():
                path = directory / (name + '.md')
                index = window.project_model.index(str(path))
                if not index.isValid():
                    raise RuntimeError('Missing tree index')
                if name.startswith('find_'):
                    window.open_find()
                    window.find_input.setText('One')
                measurements = []
                for sample in range(samples + 1):
                    window.open_file(anchor)
                    settle()
                    painted.clear()
                    started = perf_counter()
                    window.open_project_item(index)
                    returned = perf_counter()
                    settle(require_paint=True)
                    ended = perf_counter()
                    if window.editor.toPlainText() != source:
                        raise AssertionError('Loaded source changed')
                    if window.has_unsaved_changes():
                        raise AssertionError('Loaded document is dirty')
                    if sample:
                        measurements.append({
                            'handler_ms': (returned - started) * 1000,
                            'first_paint_ms': (painted[0] - started) * 1000,
                            'settled_ms': (ended - started) * 1000,
                        })
                results[name] = {key: round(statistics.median(m[key] for m in measurements), 3)
                                 for key in measurements[0]}
                print(name, results[name], flush=True)
                window.close_find()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.root, args.samples)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
