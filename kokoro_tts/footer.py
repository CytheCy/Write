"""Integrated Kokoro controls and sequential playback of locally generated chunks."""
from collections import deque
import json
import os
from pathlib import Path
import shutil
import signal
import sys

from PySide6.QtCore import QProcess, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .text_cleaning import clean_for_speech
from .voices import VOICES
from .worker import prepare_folder


def text_after_cursor(editor):
    # QTextCursor uses UTF-16 offsets; selecting through Qt also handles emoji.
    cursor = QTextCursor(editor.textCursor())
    cursor.clearSelection()
    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
    return cursor.selectedText().replace('\u2029', '\n').replace('\u2028', '\n')


class KokoroFooter(QWidget):
    closed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName('kokoroFooter')
        self.setAccessibleName('Kokoro TTS')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 7, 18, 7)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Kokoro TTS'))
        self.voice = QComboBox()
        self.voice.setAccessibleName('Kokoro voice')
        for label, voice in VOICES:
            self.voice.addItem(label, voice)
        index = self.voice.findData(window.settings.value('kokoro_voice', 'af_heart'))
        self.voice.setCurrentIndex(max(0, index))
        self.voice.currentIndexChanged.connect(
            lambda: window.settings.setValue('kokoro_voice', self.voice.currentData()))
        controls.addWidget(self.voice)
        self.start_button = QPushButton('Start')
        self.start_button.setToolTip('Read the active document from its cursor to the end')
        self.start_button.clicked.connect(self.start)
        controls.addWidget(self.start_button)
        self.pause_button = QPushButton('Pause')
        self.pause_button.setEnabled(False)
        self.pause_button.setToolTip('Pause playback; resume from the same position without generating audio again')
        self.pause_button.clicked.connect(self.toggle_pause)
        controls.addWidget(self.pause_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)
        self.status = QLabel('Ready — reads from the cursor in the active document.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.status, 1)
        close = QPushButton('Close')
        close.clicked.connect(self.close_tool)
        controls.addWidget(close)
        layout.addLayout(controls)
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        self.process.readyReadStandardOutput.connect(self.read_events)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.player = None
        self.audio_output = None
        self.queue = deque()
        self.playing = False
        self.paused = False
        self.busy = False
        self.stopped = False
        self.failed = False
        self.done = None
        self.buffer = b''
        self.errors = ''
        self.hide()

    def set_busy(self, busy):
        self.busy = busy
        self.start_button.setEnabled(not busy)
        self.voice.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.pause_button.setEnabled(busy)
        if not busy:
            self.paused = False
            self.pause_button.setText('Pause')

    def toggle_pause(self):
        if not self.busy or self.stopped or self.failed:
            return
        self.paused = not self.paused
        self.pause_button.setText('Resume' if self.paused else 'Pause')
        if self.paused:
            if self.playing:
                self.player.pause()
            self.status.setText('Paused.')
        else:
            self.status.setText('Playing…' if self.playing or self.queue else 'Waiting for audio…')
            if self.playing:
                # Keep the current source and position: play() resumes paused media.
                self.player.play()
            else:
                self.play_next()
            self.maybe_finished()

    def start(self):
        if self.busy:
            return
        text = text_after_cursor(self.window.editor)
        if not clean_for_speech(text).strip():
            self.status.setText('There is no readable text after the cursor.')
            return
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            if self.player is None:
                self.audio_output = QAudioOutput(self)
                self.player = QMediaPlayer(self)
                self.player.setAudioOutput(self.audio_output)
                self.player.mediaStatusChanged.connect(self.media_status)
                self.player.errorOccurred.connect(self.playback_error)
            python = next((shutil.which(name) for name in ('python3.12', 'python3.11', 'python3.10')
                           if shutil.which(name)), None)
            if python is None and (3, 10) <= sys.version_info[:2] < (3, 14):
                python = sys.executable
            if python is None:
                raise RuntimeError('Kokoro requires Python 3.10–3.12. Install Python 3.12 and try again.')
            # Release old media handles before clearing the previous recording.
            self.player.stop()
            self.player.setSource(QUrl())
            folder = prepare_folder(self.window.project_tree_path)
            request = folder / 'request.json'
            request.write_text(json.dumps({'text': text, 'voice': self.voice.currentData()}), encoding='utf-8')
            runtime = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'kokoro-runtime'
            self.queue.clear()
            self.playing = self.stopped = self.failed = False
            self.done = None
            self.buffer = b''
            self.errors = ''
            self.set_busy(True)
            self.status.setText('Starting Kokoro…')
            self.process.start(python, ['-m', 'kokoro_tts.worker', 'bootstrap', str(runtime), str(request)])
        except Exception as exc:
            self.status.setText(str(exc))
            self.set_busy(False)

    def read_errors(self):
        self.errors = (self.errors + bytes(self.process.readAllStandardError()).decode('utf-8', 'replace'))[-4000:]

    def read_events(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if self.stopped or self.failed:
                continue
            if 'error' in event:
                self.failed = True
                self.queue.clear()
                if self.player:
                    self.player.stop()
                self.playing = False
                self.status.setText('Kokoro: ' + event['error'])
            elif 'audio' in event:
                self.queue.append(event['audio'])
                if not self.paused:
                    self.status.setText(f"Generated {event['current']} of {event['total']} chunks; playing…")
                self.play_next()
            elif 'done' in event:
                self.done = event['done']
            elif 'status' in event and not self.paused:
                self.status.setText(event['status'])

    def play_next(self):
        if self.paused or self.playing or not self.queue or self.stopped or self.failed:
            return
        self.playing = True
        self.player.setSource(QUrl.fromLocalFile(self.queue.popleft()))
        self.player.play()

    def media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.playing = False
            self.play_next()
            self.maybe_finished()

    def playback_error(self, *_):
        if not self.busy or self.stopped:
            return
        message = self.player.errorString()
        self.stop()
        self.status.setText('Audio playback failed: ' + message)

    def process_finished(self, code, _status):
        self.read_events()
        self.read_errors()
        if not self.stopped and not self.failed and (code or not self.done):
            self.failed = True
            self.queue.clear()
            if self.player:
                self.player.stop()
            self.playing = False
            self.status.setText('Kokoro generation failed. ' + self.errors[-1500:])
        self.maybe_finished()

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.failed = True
            self.status.setText('Could not start Kokoro: ' + self.process.errorString())
            self.set_busy(False)

    def maybe_finished(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        if not self.playing and not self.queue:
            self.set_busy(False)
            if self.done and not self.stopped and not self.failed:
                self.status.setText('Finished — ' + self.done)

    def stop(self):
        self.stopped = True
        self.paused = False
        self.pause_button.setText('Pause')
        self.queue.clear()
        self.playing = False
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        if self.process.state() != QProcess.ProcessState.NotRunning:
            pid = self.process.processId()
            try:
                if os.name == 'posix' and os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGKILL)
                else:
                    self.process.kill()
            except ProcessLookupError:
                pass
        self.status.setText('Stopped.')
        self.maybe_finished()

    def close_tool(self):
        self.stop()
        self.hide()
        self.closed.emit()

    def shutdown(self):
        self.stop()
        self.process.waitForFinished(3000)
