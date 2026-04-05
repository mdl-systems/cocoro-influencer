"""
設定管理モジュール
.env ファイルから環境変数を読み込み、型安全な設定オブジェクトを提供する。
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

def _load_env():
    """config/.env から環境変数をロード"""
    env_path = PROJECT_ROOT / "config" / ".env"
    if not env_path.exists():
        print(f"[WARN] .env ファイルが見つかりません: {env_path}")
        print("       config/.env.example をコピーして設定してください。")
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if not os.environ.get(key):
                    os.environ[key] = value


@dataclass
class GPUConfig:
    cuda_devices: str = "0"
    vram_limit: int = 24576  # MB


@dataclass
class ComfyUIConfig:
    host: str = "127.0.0.1"
    port: int = 8188
    path: str = r"C:\ComfyUI"
    enable_xformers: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"


@dataclass
class BlenderConfig:
    path: str = r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
    render_engine: str = "EEVEE"
    render_width: int = 1024
    render_height: int = 1024


@dataclass
class ModelPaths:
    flux: str = "models/flux1-dev.safetensors"
    controlnet_canny: str = "models/controlnet-canny.safetensors"
    controlnet_depth: str = "models/controlnet-depth.safetensors"
    wan21: str = "models/wan21-i2v.safetensors"
    liveportrait: str = "models/liveportrait/"


@dataclass
class TTSConfig:
    engine: str = "style_bert_vits2"
    style_bert_path: str = r"C:\StyleBERT-VITS2"
    style_bert_model: str = "jvnv-F1-jp"
    openai_api_key: str = ""
    openai_tts_voice: str = "nova"


@dataclass
class FFmpegConfig:
    path: str = r"C:\ffmpeg\bin\ffmpeg.exe"
    hwaccel: str = ""
    encoder: str = "libx264"
    quality: int = 23


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    secret_key: str = "change-me"
    gpurental_url: str = "https://gpurental.jp/api"
    gpurental_key: str = ""


@dataclass
class JobConfig:
    max_concurrent: int = 1
    timeout: int = 3600
    output_dir: str = "output"
    log_level: str = "INFO"


@dataclass
class Settings:
    """全設定を統合するルートクラス"""
    gpu: GPUConfig = field(default_factory=GPUConfig)
    comfyui: ComfyUIConfig = field(default_factory=ComfyUIConfig)
    blender: BlenderConfig = field(default_factory=BlenderConfig)
    models: ModelPaths = field(default_factory=ModelPaths)
    tts: TTSConfig = field(default_factory=TTSConfig)
    ffmpeg: FFmpegConfig = field(default_factory=FFmpegConfig)
    api: APIConfig = field(default_factory=APIConfig)
    job: JobConfig = field(default_factory=JobConfig)


def load_settings() -> Settings:
    """環境変数から設定を読み込み、Settingsオブジェクトを生成"""
    _load_env()

    def _env(key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    def _env_int(key: str, default: int = 0) -> int:
        val = os.environ.get(key, "")
        return int(val) if val.isdigit() else default

    def _env_bool(key: str, default: bool = False) -> bool:
        val = os.environ.get(key, "").lower()
        return val in ("true", "1", "yes") if val else default

    return Settings(
        gpu=GPUConfig(
            cuda_devices=_env("CUDA_VISIBLE_DEVICES", "0"),
            vram_limit=_env_int("GPU_VRAM_LIMIT", 24576),
        ),
        comfyui=ComfyUIConfig(
            host=_env("COMFYUI_HOST", "127.0.0.1"),
            port=_env_int("COMFYUI_PORT", 8188),
            path=_env("COMFYUI_PATH", r"C:\ComfyUI"),
            enable_xformers=_env_bool("COMFYUI_ENABLE_XFORMERS", True),
        ),
        blender=BlenderConfig(
            path=_env("BLENDER_PATH", r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
            render_engine=_env("BLENDER_RENDER_ENGINE", "EEVEE_NEXT"),
            render_width=_env_int("RENDER_WIDTH", 1024),
            render_height=_env_int("RENDER_HEIGHT", 1024),
        ),
        models=ModelPaths(
            flux=_env("FLUX_MODEL_PATH", "models/flux1-dev.safetensors"),
            controlnet_canny=_env("CONTROLNET_CANNY_PATH", "models/controlnet-canny.safetensors"),
            controlnet_depth=_env("CONTROLNET_DEPTH_PATH", "models/controlnet-depth.safetensors"),
            wan21=_env("WAN21_MODEL_PATH", "models/wan21-i2v.safetensors"),
            liveportrait=_env("LIVEPORTRAIT_MODEL_PATH", "models/liveportrait/"),
        ),
        tts=TTSConfig(
            engine=_env("TTS_ENGINE", "style_bert_vits2"),
            style_bert_path=_env("STYLE_BERT_VITS2_PATH", r"C:\StyleBERT-VITS2"),
            style_bert_model=_env("STYLE_BERT_VITS2_MODEL", "jvnv-F1-jp"),
            openai_api_key=_env("OPENAI_API_KEY", ""),
            openai_tts_voice=_env("OPENAI_TTS_VOICE", "nova"),
        ),
        ffmpeg=FFmpegConfig(
            path=_env("FFMPEG_PATH", r"C:\ffmpeg\bin\ffmpeg.exe"),
            hwaccel=_env("FFMPEG_HWACCEL", ""),
            encoder=_env("FFMPEG_ENCODER", "libx264"),
            quality=_env_int("FFMPEG_QUALITY", 23),
        ),
        api=APIConfig(
            host=_env("API_HOST", "0.0.0.0"),
            port=_env_int("API_PORT", 8080),
            secret_key=_env("API_SECRET_KEY", "change-me"),
            gpurental_url=_env("GPURENTAL_API_URL", "https://gpurental.jp/api"),
            gpurental_key=_env("GPURENTAL_API_KEY", ""),
        ),
        job=JobConfig(
            max_concurrent=_env_int("MAX_CONCURRENT_JOBS", 1),
            timeout=_env_int("JOB_TIMEOUT", 3600),
            output_dir=_env("OUTPUT_DIR", "output"),
            log_level=_env("LOG_LEVEL", "INFO"),
        ),
    )


# シングルトンインスタンス
settings = load_settings()

if __name__ == "__main__":
    import json
    from dataclasses import asdict
    s = load_settings()
    print(json.dumps(asdict(s), indent=2, ensure_ascii=False))
