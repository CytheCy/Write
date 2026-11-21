"""Write's private speech worker. Stdout is a JSON-lines protocol to the footer."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import wave

from .chunking import streaming_chunks
from .text_cleaning import clean_for_speech
from .voices import language_for_voice


def emit(**event):
    print(json.dumps(event), flush=True)


def prepare_folder(root: Path) -> Path:
    """Remove only Write's speech artifacts; never follow project symlinks."""
    folder = root / 'Kodoro'
    if folder.is_symlink():
        raise ValueError('Kodoro must be a real folder, not a symbolic link.')
    folder.mkdir(exist_ok=True)
    for path in folder.iterdir():
        if (re.fullmatch(r'chunk-\d+\.(txt|wav)', path.name)
                or path.name in {'request.json', 'final.wav', 'final.partial.wav'}):
            if path.is_file() or path.is_symlink():
                path.unlink()
    return folder


def ensure_runtime(runtime: Path):
    """Provision an app-owned Python environment, independent of Kokoro Reader."""
    python = runtime / 'bin/python'
    marker = runtime / 'write-runtime-v1'
    if not marker.exists():
        emit(status='Setting up speech dependencies (first use may take several minutes)…')
        runtime.parent.mkdir(parents=True, exist_ok=True)
        if not python.exists():
            subprocess.run([sys.executable, '-m', 'venv', str(runtime)], check=True,
                           stdout=sys.stderr)
        subprocess.run([str(python), '-m', 'pip', 'install', '--index-url',
                        'https://download.pytorch.org/whl/cpu', 'torch'],
                       check=True, stdout=sys.stderr)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                        str(Path(__file__).with_name('runtime-requirements.txt'))],
                       check=True, stdout=sys.stderr)
        marker.touch()
    os.execv(str(python), [str(python), '-m', 'kokoro_tts.worker', 'generate', sys.argv[3]])


def generate(request_path: Path, pipeline_factory=None):
    request = json.loads(request_path.read_text(encoding='utf-8'))
    folder = request_path.parent
    chunks = streaming_chunks(clean_for_speech(request['text']))
    if not chunks:
        raise ValueError('There is no readable text after the cursor.')
    for index, chunk in enumerate(chunks, 1):
        (folder / f'chunk-{index:05}.txt').write_text(chunk, encoding='utf-8')
    emit(status='Loading Kokoro-82M (first use may download model and voice)…')
    # Third-party progress/log output must not corrupt the protocol.
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        if pipeline_factory is None:
            from kokoro import KPipeline
            pipeline_factory = KPipeline
        pipeline = pipeline_factory(lang_code=language_for_voice(request['voice']))
    partial = folder / 'final.partial.wav'
    try:
        with wave.open(str(partial), 'wb') as final:
            final.setnchannels(1)
            final.setsampwidth(2)
            final.setframerate(24000)
            for index, chunk in enumerate(chunks, 1):
                path = folder / f'chunk-{index:05}.wav'
                frames = 0
                with wave.open(str(path), 'wb') as output:
                    output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                    with contextlib.redirect_stdout(sys.stderr):
                        for _, _, audio in pipeline(chunk, voice=request['voice']):
                            if audio is None:
                                continue
                            if hasattr(audio, 'detach'):
                                audio = audio.detach().cpu().numpy()
                            pcm = (np.clip(np.asarray(audio).reshape(-1), -1, 1) * 32767).astype('<i2').tobytes()
                            output.writeframesraw(pcm)
                            final.writeframesraw(pcm)
                            frames += len(pcm)
                        if frames and index < len(chunks):
                            pause = bytes(round(24000 * .16) * 2)
                            output.writeframesraw(pause)
                            final.writeframesraw(pause)
                if not frames:
                    raise ValueError(f'Kokoro produced no audio for chunk {index}.')
                emit(audio=str(path), current=index, total=len(chunks))
        partial.replace(folder / 'final.wav')
        emit(done=str(folder / 'final.wav'))
    finally:
        partial.unlink(missing_ok=True)


def main():
    if os.name == 'posix' and os.getpgrp() != os.getpid():
        os.setsid()
    try:
        if sys.argv[1] == 'bootstrap':
            ensure_runtime(Path(sys.argv[2]))
        else:
            generate(Path(sys.argv[2]))
    except Exception as exc:
        emit(error=str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
