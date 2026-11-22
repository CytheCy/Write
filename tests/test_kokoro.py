"""Speech chunk artifacts, cursor snapshots, protocol, and footer lifecycle."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QProcess, QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from kokoro_tts.chunking import streaming_chunks
from kokoro_tts.footer import text_after_cursor
from kokoro_tts.worker import generate, prepare_folder
from main import MainWindow


class ChunkTests(unittest.TestCase):
    def test_opening_short_and_later_chunks_preserve_words(self):
        text = ' '.join(f'word{i}' for i in range(200))
        chunks = streaming_chunks(text)
        self.assertLessEqual(len(chunks[0]), 120)
        self.assertTrue(all(len(c) <= 300 for c in chunks))
        self.assertEqual(' '.join(chunks), text)

    def test_cleanup_removes_old_artifacts_and_preserves_other_files(self):
        with tempfile.TemporaryDirectory() as root:
            folder = prepare_folder(Path(root))
            self.assertEqual(folder, Path(root) / '.app' / '.kokoro')
            self.assertTrue(folder.is_dir())
            sibling = folder.parent / 'other-app-data.txt'
            sibling.touch()
            for name in ('chunk-00001.txt', 'chunk-00001.wav', 'final.wav', 'final.partial.wav', 'request.json', 'notes.md'):
                (folder / name).touch()
            prepare_folder(Path(root))
            self.assertEqual([p.name for p in folder.iterdir()], ['notes.md'])
            self.assertTrue(sibling.exists())

    def test_cleanup_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            app_folder = Path(root) / '.app'
            app_folder.mkdir()
            (app_folder / '.kokoro').symlink_to(other)
            with self.assertRaises(ValueError):
                prepare_folder(Path(root))

    def test_cleanup_rejects_app_symlink(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            (Path(root) / '.app').symlink_to(other)
            with self.assertRaises(ValueError):
                prepare_folder(Path(root))
            self.assertFalse((Path(other) / '.kokoro').exists())

    def test_worker_streams_ordered_chunks_and_final_wave_matches(self):
        # Uses a deterministic pipeline; no model download in the unit suite.
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy is needed for the synthesis test')
        def factory(**_):
            def pipeline(text, **_):
                yield text, '', np.array([-.5, 0, .5], dtype=np.float32)
            return pipeline
        with tempfile.TemporaryDirectory() as root:
            folder = prepare_folder(Path(root))
            request = folder / 'request.json'
            request.write_text(json.dumps({'text': 'Hello world. ' * 80, 'voice': 'af_heart'}))
            events = io.StringIO()
            with contextlib.redirect_stdout(events):
                generate(request, factory)
            events = [json.loads(line) for line in events.getvalue().splitlines()]
            audio = [e for e in events if 'audio' in e]
            self.assertGreater(len(audio), 2)
            self.assertEqual([e['current'] for e in audio], list(range(1, len(audio) + 1)))
            combined = b''
            for event in audio:
                with wave.open(event['audio']) as chunk:
                    combined += chunk.readframes(chunk.getnframes())
                self.assertTrue(Path(event['audio']).with_suffix('.txt').exists())
            with wave.open(str(folder / 'final.wav')) as final:
                self.assertEqual(final.getframerate(), 24000)
                self.assertEqual(final.readframes(final.getnframes()), combined)
            self.assertFalse((folder / 'final.partial.wav').exists())
            self.assertEqual(events[-1]['done'], str(folder / 'final.wav'))


class FooterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('project_tree_path', str(Path(settings.fileName()).parent))
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow()
        self.window.set_project_tree_path(Path(self.temp.name))
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._updating = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_button_opens_footer_and_close_unchecks(self):
        button = self.window.ribbon_buttons['Kokoro TTS']
        button.click()
        self.assertTrue(self.window.kokoro_footer.isVisible())
        self.assertTrue(button.isChecked())
        self.window.kokoro_footer.close_tool()
        self.assertFalse(button.isChecked())
        self.assertFalse(self.window.kokoro_footer.isVisible())

    def test_cursor_snapshot_handles_utf16_and_selection(self):
        editor = self.window.editor
        editor.setPlainText('Before 😀\nRead this.\nAnd this.')
        cursor = editor.document().find('Read')
        cursor.setPosition(cursor.selectionStart())
        editor.setTextCursor(cursor)
        self.assertEqual(text_after_cursor(editor), 'Read this.\nAnd this.')

    def test_start_snapshots_active_document_and_clears_previous_run(self):
        footer = self.window.kokoro_footer
        self.window.editor.setPlainText('Skip. Read me.')
        cursor = self.window.editor.textCursor()
        cursor.setPosition(6)
        self.window.editor.setTextCursor(cursor)
        folder = prepare_folder(Path(self.temp.name))
        (folder / 'chunk-00001.wav').touch()
        with patch.object(footer.process, 'start') as start:
            footer.start()
        start.assert_called_once()
        self.assertEqual(folder, Path(self.temp.name) / '.app' / '.kokoro')
        self.assertEqual(start.call_args.args[1][-1], str(folder / 'request.json'))
        self.assertFalse((folder / 'chunk-00001.wav').exists())
        self.assertEqual(json.loads((folder / 'request.json').read_text())['text'], 'Read me.')
        self.assertFalse(footer.start_button.isEnabled())
        footer.stop()
        self.assertTrue(footer.start_button.isEnabled())
        self.assertFalse(footer.queue)

    def test_empty_tail_does_not_delete_previous_audio(self):
        folder = prepare_folder(Path(self.temp.name))
        final = folder / 'final.wav'
        final.touch()
        self.window.editor.clear()
        self.window.kokoro_footer.start()
        self.assertTrue(final.exists())
        self.assertFalse(self.window.kokoro_footer.busy)

    def test_voice_is_persisted(self):
        footer = self.window.kokoro_footer
        footer.voice.setCurrentIndex(2)
        self.assertEqual(self.window.settings.value('kokoro_voice'), 'af_nicole')

    def test_protocol_queues_chunks_in_order_and_waits_for_playback(self):
        footer = self.window.kokoro_footer
        footer.player = Mock()
        footer.set_busy(True)
        payload = (b'library log\n' + json.dumps({'audio': '/tmp/one.wav', 'current': 1, 'total': 2}).encode()
                   + b'\n' + json.dumps({'audio': '/tmp/two.wav', 'current': 2, 'total': 2}).encode() + b'\n')
        with patch.object(footer.process, 'readAllStandardOutput', return_value=payload):
            footer.read_events()
        self.assertTrue(footer.playing)
        self.assertEqual(list(footer.queue), ['/tmp/two.wav'])
        footer.player.play.assert_called_once()
        footer.maybe_finished()
        self.assertTrue(footer.busy)
        footer.stop()
        self.assertFalse(footer.queue)
        self.assertFalse(footer.busy)

    def test_stop_terminates_worker_and_restores_controls(self):
        import sys
        footer = self.window.kokoro_footer
        footer.process.start(sys.executable, ['-c', 'import time; time.sleep(30)'])
        self.assertTrue(footer.process.waitForStarted(3000))
        footer.set_busy(True)
        footer.stop()
        self.assertTrue(footer.process.waitForFinished(3000))
        self.app.processEvents()
        self.assertEqual(footer.process.state(), QProcess.ProcessState.NotRunning)
        self.assertFalse(footer.busy)
        self.assertEqual(footer.status.text(), 'Stopped.')

    def test_pause_resumes_current_audio_without_restarting_generation(self):
        footer = self.window.kokoro_footer
        footer.player = Mock()
        footer.set_busy(True)
        footer.queue.extend(['/tmp/one.wav', '/tmp/two.wav'])
        footer.play_next()
        footer.player.reset_mock()
        with patch.object(footer.process, 'start') as start, \
                patch('kokoro_tts.footer.prepare_folder') as prepare:
            footer.pause_button.click()
            self.assertTrue(footer.paused)
            self.assertEqual(footer.pause_button.text(), 'Resume')
            footer.player.pause.assert_called_once()
            footer.maybe_finished()
            self.assertTrue(footer.busy)
            footer.pause_button.click()
            self.assertFalse(footer.paused)
            self.assertEqual(footer.pause_button.text(), 'Pause')
            footer.player.play.assert_called_once()
            footer.player.setSource.assert_not_called()
            footer.player.stop.assert_not_called()
            start.assert_not_called()
            prepare.assert_not_called()
        self.assertEqual(list(footer.queue), ['/tmp/two.wav'])

    def test_chunks_generated_while_paused_wait_for_resume(self):
        from PySide6.QtMultimedia import QMediaPlayer
        footer = self.window.kokoro_footer
        footer.player = Mock()
        footer.set_busy(True)
        footer.pause_button.click()
        payload = (json.dumps({'audio': '/tmp/one.wav', 'current': 1, 'total': 1})
                   + '\n' + json.dumps({'done': '/tmp/final.wav'}) + '\n').encode()
        with patch.object(footer.process, 'readAllStandardOutput', return_value=payload):
            footer.process_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertEqual(footer.status.text(), 'Paused.')
        self.assertTrue(footer.busy)
        self.assertEqual(list(footer.queue), ['/tmp/one.wav'])
        footer.player.play.assert_not_called()
        footer.pause_button.click()
        footer.player.play.assert_called_once()
        self.assertEqual(footer.player.setSource.call_args.args[0].toLocalFile(), '/tmp/one.wav')
        footer.media_status(QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertFalse(footer.busy)
        self.assertFalse(footer.pause_button.isEnabled())
        self.assertEqual(footer.status.text(), 'Finished — /tmp/final.wav')

    def test_stop_while_paused_clears_playback_and_pause_controls(self):
        footer = self.window.kokoro_footer
        footer.player = Mock()
        footer.set_busy(True)
        footer.queue.append('/tmp/one.wav')
        footer.play_next()
        footer.pause_button.click()
        footer.stop_button.click()
        self.assertFalse(footer.paused)
        self.assertFalse(footer.playing)
        self.assertFalse(footer.busy)
        self.assertFalse(footer.pause_button.isEnabled())
        self.assertEqual(footer.pause_button.text(), 'Pause')
        self.assertEqual(footer.status.text(), 'Stopped.')
