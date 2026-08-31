from app.config import AppConfig, resolve_lid_runtime
from app.core.language_detection import validate_lid_model


def test_bundled_lid_discovery_preserves_custom_path(tmp_path):
    path = tmp_path / 'models/lid/ggml-tiny.bin'
    path.parent.mkdir(parents=True)
    path.touch()
    config = AppConfig()
    assert resolve_lid_runtime(config, [tmp_path])
    assert config.asr_qwen3_lid_model_path == str(path)
    config.asr_qwen3_lid_model_path = 'missing-custom.bin'
    assert not resolve_lid_runtime(config, [tmp_path])
    assert config.asr_qwen3_lid_model_path == 'missing-custom.bin'


def test_whisper_auto_and_explicit_qwen_language_need_no_lid():
    assert validate_lid_model('whisper', 'auto', '') is None
    assert validate_lid_model('qwen3-1.7b', 'ja', '') is None
