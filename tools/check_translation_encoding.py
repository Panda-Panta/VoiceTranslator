from __future__ import annotations

from app.config import ConfigStore
from app.core.llama_server_manager import LlamaServerManager
from app.core.translator import LocalTranslator
from app.models import TranscriptionSegment


def main() -> int:
    config = ConfigStore().load()
    server = LlamaServerManager(config.llama_server_path)
    try:
        server.start(
            config.translation_model_path,
            config.translation_port,
            config.translation_gpu_layers,
            config.translation_context_size,
            timeout=config.server_start_timeout,
        )
        result = LocalTranslator(server.base_url, batch_size=1, temperature=0.7).translate(
            [TranscriptionSegment(1, 0, 1, "Hello, world!")], "English", "中文"
        )[0].translated_text
        print(ascii(result))
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
