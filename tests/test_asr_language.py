import os
import struct
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.config import AppConfig, ConfigStore
from app.core.crispasr_engine import CrispASREngine
from app.core.pipeline import ProcessingPipeline
from app.models import ProcessingTask, ProcessMode
from app.views.home_interface import HomeInterface


def lid_file(tmp_path):
    path = tmp_path / 'ggml-tiny.bin'
    with path.open('wb') as stream:
        stream.write(struct.pack('<II', 0x67676d6c, 51865))
        stream.truncate(2 * 1024 * 1024)
    return path


def test_home_source_language_is_saved_and_reaches_task(tmp_path):
    application = QApplication.instance() or QApplication([])
    config = AppConfig(asr_language='ja')
    store = ConfigStore(tmp_path / 'config.json')
    page = HomeInterface(config, store=store)
    assert page.source_language.currentText() == '日本語'
    page.source_language.setCurrentText('English')
    assert config.asr_language == 'en'
    assert store.load().asr_language == 'en'
    audio = tmp_path / 'test.wav'
    audio.touch()
    page.add_files([str(audio)])
    with patch.object(QThread, 'start'):
        page._start()
    assert page._worker.task.source_language == 'English'
    assert page._worker.task.target_language == page.target_language.currentText()
    page._worker = None
    page.close()


def test_missing_lid_rejected_before_process_start(tmp_path):
    for name in ('crispasr.exe', 'main.gguf', 'align.gguf', 'sample.wav'):
        (tmp_path / name).touch()
    engine = CrispASREngine(str(tmp_path / 'crispasr.exe'), str(tmp_path / 'main.gguf'),
                            backend='qwen3-1.7b', aligner_model_path=str(tmp_path / 'align.gguf'),
                            lid_model_path=str(tmp_path / 'missing.bin'))
    with patch('app.core.crispasr_engine.subprocess.Popen') as popen:
        with pytest.raises(ValueError, match='语言检测'):
            engine.transcribe(str(tmp_path / 'sample.wav'))
        popen.assert_not_called()


def test_missing_lid_rejected_before_extraction_or_separation(tmp_path):
    video = tmp_path / 'sample.mkv'
    video.touch()
    config = AppConfig(asr_backend='qwen3-1.7b', asr_qwen3_lid_model_path=str(tmp_path / 'missing.bin'),
                       vocal_separation_enabled=True)
    pipeline = ProcessingPipeline(config)
    with patch('app.core.pipeline.FileHandler.extract_audio') as extract:
        with pytest.raises(ValueError, match='语言检测'):
            pipeline.run(ProcessingTask(input_files=[str(video)], process_mode=ProcessMode.TRANSCRIBE_ONLY))
        extract.assert_not_called()


def test_local_lid_is_explicit_and_japanese_bypasses_it(tmp_path):
    lid = lid_file(tmp_path)
    engine = CrispASREngine('crispasr', 'qwen.gguf', backend='qwen3-1.7b', lid_model_path=str(lid))
    command = engine._build_command(Path('crispasr'), Path('qwen.gguf'), Path('a.wav'), Path('out'))
    assert command[command.index('--lid-model') + 1] == str(lid.resolve())
    assert command[command.index('--lid-backend') + 1] == 'whisper'
    engine.language = 'ja'
    engine.lid_model_path = 'missing.bin'
    command = engine._build_command(Path('crispasr'), Path('qwen.gguf'), Path('a.wav'), Path('out'))
    assert '--lid-model' not in command


@pytest.mark.parametrize('extra', ['--language auto', '-l auto', '--language=auto', '--lid-model auto', '--lid-backend silero'])
def test_extra_arguments_cannot_bypass_language_preflight(extra, tmp_path):
    engine = CrispASREngine('crispasr', 'qwen.gguf', backend='qwen3-1.7b', language='ja', extra_args=extra)
    with pytest.raises(ValueError, match='源语言|语言检测'):
        engine._build_command(Path('crispasr'), Path('qwen.gguf'), Path('a.wav'), Path('out'))


@pytest.mark.parametrize('contents', [b'', b'<html>error</html>', struct.pack('<II', 0x67676d6c, 51864)])
def test_invalid_lid_rejected(contents, tmp_path):
    lid = tmp_path / 'bad.bin'
    lid.write_bytes(contents)
    engine = CrispASREngine('crispasr', 'qwen.gguf', backend='qwen3-1.7b', lid_model_path=str(lid))
    with pytest.raises(ValueError, match='语言检测'):
        engine._build_command(Path('crispasr'), Path('qwen.gguf'), Path('a.wav'), Path('out'))
