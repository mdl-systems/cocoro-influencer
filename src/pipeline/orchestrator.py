"""orchestrator.py: パイプライン全体制御モジュール

台本YAML → 音声 → 画像 → 動画 → 合成 の
フルパイプラインを順番に実行する。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.engines.echomimic_engine import EchoMimicEngine
from src.engines.flux_engine import FluxEngine
from src.engines.manager import EngineManager
from src.engines.voice_engine import VoiceEngine
from src.engines.wan_engine import WanEngine
from src.pipeline.compositor import Caption, CompositeConfig, Compositor

logger = logging.getLogger(__name__)


@dataclass
class ScriptScene:
    """台本の1シーン定義"""

    text: str                           # ナレーションテキスト
    scene_type: str = "talking_head"    # "talking_head" | "cinematic"
    cinematic_prompt: str = ""          # シネマティック用プロンプト
    caption: str = ""                   # テロップテキスト


@dataclass
class PipelineConfig:
    """パイプライン設定"""

    scenes: list[ScriptScene]
    avatar_prompt: str                           # アバター画像生成プロンプト
    output_dir: Path                             # 出力ディレクトリ
    lora_path: Path | None = None               # LoRAパス (オプション)
    bgm_path: Path | None = None               # BGMパス (オプション)
    output_format: str = "youtube"              # 出力フォーマット
    flux_model_id: str = "black-forest-labs/FLUX.1-dev"
    wan_model_id: str = "Wan-AI/Wan2.1-I2V-14B-720P-Diffusers"
    voicevox_url: str = "http://localhost:50021"
    speaker_id: int = 3
    avatar_seed: int | None = None


class Orchestrator:
    """フルパイプライン実行クラス

    EngineManagerでGPUメモリを管理しながら
    各エンジンを順番に呼び出す。
    """

    def __init__(self, config: PipelineConfig) -> None:
        """Orchestratorの初期化

        Args:
            config: パイプライン設定
        """
        self._config = config
        self._manager = EngineManager()
        self._compositor = Compositor()

        # 全エンジンを登録
        self._manager.register("flux", FluxEngine(config.flux_model_id))
        self._manager.register("wan", WanEngine(config.wan_model_id))
        self._manager.register("echomimic", EchoMimicEngine())
        self._manager.register("voice", VoiceEngine(config.voicevox_url, config.speaker_id))

    def run(self) -> Path:
        """フルパイプラインを実行する

        Returns:
            生成した最終動画ファイルのパス
        """
        config = self._config
        config.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Orchestrator: パイプライン開始 (scenes=%d)", len(config.scenes))

        # Step 1: アバター画像生成
        avatar_path = config.output_dir / "avatar.png"
        if not avatar_path.exists():
            logger.info("Orchestrator: [1/4] アバター画像生成")
            engine = self._manager.get("flux")
            engine.generate(
                prompt=config.avatar_prompt,
                output_path=avatar_path,
                lora_path=config.lora_path,
                seed=config.avatar_seed,
            )
        else:
            logger.info("Orchestrator: [1/4] アバター画像は既に存在します (%s)", avatar_path)

        clip_paths: list[Path] = []
        captions: list[Caption] = []
        elapsed: float = 0.0

        # Step 2 & 3: シーンごとに音声→動画生成
        for i, scene in enumerate(config.scenes):
            logger.info(
                "Orchestrator: シーン %d/%d (type=%s)",
                i + 1, len(config.scenes), scene.scene_type,
            )

            # Step 2: 音声生成
            audio_path = config.output_dir / f"scene_{i:03d}_voice.wav"
            if not audio_path.exists():
                voice_engine = self._manager.get("voice")
                voice_engine.generate(text=scene.text, output_path=audio_path)

            # 音声長を取得
            import wave
            with wave.open(str(audio_path), "rb") as wf:
                audio_duration = wf.getnframes() / wf.getframerate()

            # Step 3: 動画生成
            clip_path = config.output_dir / f"scene_{i:03d}_clip.mp4"
            if not clip_path.exists():
                if scene.scene_type == "cinematic":
                    wan_engine = self._manager.get("wan")
                    wan_engine.generate(
                        image_path=avatar_path,
                        prompt=scene.cinematic_prompt or scene.text,
                        output_path=clip_path,
                    )
                else:
                    # デフォルト: トーキングヘッド
                    echo_engine = self._manager.get("echomimic")
                    echo_engine.generate(
                        image_path=avatar_path,
                        audio_path=audio_path,
                        output_path=clip_path,
                    )

            clip_paths.append(clip_path)

            # テロップ登録
            if scene.caption:
                captions.append(Caption(
                    text=scene.caption,
                    start_time=elapsed,
                    end_time=elapsed + audio_duration,
                ))
            elapsed += audio_duration

        # Step 4: 動画合成
        logger.info("Orchestrator: [4/4] 動画合成")
        final_path = config.output_dir / "final.mp4"
        composite_config = CompositeConfig(
            clips=clip_paths,
            output_path=final_path,
            bgm_path=config.bgm_path,
            captions=captions,
            output_format=config.output_format,
        )
        self._compositor.compose(composite_config)

        logger.info("Orchestrator: パイプライン完了 → %s", final_path)
        self._manager.unload_all()
        return final_path
