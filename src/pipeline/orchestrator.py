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
    cinematic_prompt: str = ""
    pose: str = "neutral"
    appearance_prompt: str = ""          # シネマティック用プロンプト
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
    voicevox_url: str = "http://localhost:5000"
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

    async def run(self) -> Path:
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
                    # デフォルト: Kling AI I2V → Sync.so リップシンク
                    from src.modules.video_gen.kling import KlingAPIClient
                    from src.modules.lipsync.sync_so import LipSyncAPIClient
                    import asyncio, base64

                    async def run_video_pipeline():
                        kling = KlingAPIClient()
                        # poseに応じてInstantID生成済み画像を選択
                        pose_image_map = {
                            "neutral": "avatar_neutral_upper.png",
                            "greeting": "avatar_greeting_full.png",
                            "walk": "avatar_walking_full.png",
                            "fullbody": "avatar_fullbody_ref_gen.png",
                        }
                        pose_img_name = pose_image_map.get(scene.pose, "avatar.png")
                        pose_img_path = config.output_dir / pose_img_name
                        if pose_img_path.exists():
                            image_data_url = str(pose_img_path.resolve())
                            logger.info("Pose画像使用: %s", image_data_url)
                        else:
                            image_data_url = str(avatar_path.resolve())
                            logger.info("デフォルト画像使用: %s", image_data_url)
                        # poseとcinematic_promptを組み合わせてKlingプロンプト生成
                        pose_map = {
                            "neutral": "natural pose, looking at camera",
                            "greeting": "waving hand, greeting gesture, friendly smile",
                            "walk": "walking naturally, dynamic movement",
                            "fullbody": "full body, standing naturally",
                        }
                        pose_desc = pose_map.get(scene.pose, "natural pose")
                        kling_prompt = scene.cinematic_prompt or "studio lighting, professional setting"
                        if scene.appearance_prompt:
                            kling_prompt = f"{scene.appearance_prompt}, {kling_prompt}"
                        kling_prompt = f"{pose_desc}, {kling_prompt}, talking head video"
                        logger.info("Kling prompt: %s", kling_prompt)
                        task_id = await kling.submit_i2v_task(
                            image_url=image_data_url,
                            prompt=kling_prompt,
                            duration=5 if audio_duration <= 5 else 10,
                        )
                        video_url = await kling.wait_for_task(task_id)
                        lipsync = LipSyncAPIClient()
                        # WAV→MP3変換
                        import subprocess as _sp
                        mp3_path = audio_path.with_suffix('.mp3')
                        _sp.run(['ffmpeg', '-i', str(audio_path), str(mp3_path), '-y'], check=True)
                        # Kling動画をローカルにダウンロード＆再エンコード
                        import httpx as _httpx
                        kling_raw_path = clip_path.with_name(clip_path.stem + '_kling_raw.mp4')
                        kling_video_path = clip_path.with_name(clip_path.stem + '_kling.mp4')
                        async with _httpx.AsyncClient(timeout=120.0) as _hc:
                            _r = await _hc.get(video_url)
                            kling_raw_path.write_bytes(_r.content)
                        # H.264/AAC再エンコード
                        _sp.run([
                            'ffmpeg', '-i', str(kling_raw_path),
                            '-c:v', 'libx264', '-c:a', 'aac',
                            '-movflags', '+faststart',
                            str(kling_video_path), '-y'
                        ], check=True)
                        # Wav2Lipリップシンク自動実行
                        lipsync_path = clip_path.with_name(clip_path.stem + '_lipsync.mp4')
                        logger.info("Wav2Lip リップシンク開始: %s", lipsync_path)
                        _sp.run([
                            '/mnt/models/Wav2Lip/venv/bin/python',
                            '/mnt/models/Wav2Lip/inference.py',
                            '--checkpoint_path', '/mnt/models/Wav2Lip/checkpoints/wav2lip_gan.pth',
                            '--face', str(kling_video_path),
                            '--audio', str(audio_path),
                            '--outfile', str(lipsync_path),
                        ], check=True, cwd='/mnt/models/Wav2Lip')
                        import shutil as _sh
                        _sh.copy(str(lipsync_path), str(clip_path))
                        logger.info("Wav2Lip リップシンク完了: %s", clip_path)

                    await run_video_pipeline()

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
