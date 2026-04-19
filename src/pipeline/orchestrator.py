"""orchestrator.py: パイプライン全体制御モジュール

台本YAML → 音声 → 画像 → 動画 → 合成 の
フルパイプラインを順番に実行する。

単体シーン生成 (run_single_scene) も提供。

## サーバー別環境変数設定 (config/.env)
  WAV2LIP_PYTHON  : Wav2Lip venv の python パス
  WAV2LIP_DIR     : Wav2Lip リポジトリのルートディレクトリ
  WAN2_PYTHON     : Wan2.1 venv の python パス
  WAN2_MODEL_PATH : Wan2.1 モデルのローカルパス

## デフォルト値 (cocoro-server-01用)
  WAV2LIP_PYTHON  = /mnt/models/Wav2Lip/venv/bin/python
  WAV2LIP_DIR     = /mnt/models/Wav2Lip
  WAN2_PYTHON     = /data/venv/wan2/bin/python
  WAN2_MODEL_PATH = /data/models/Wan2.1/I2V-14B-480P
"""

import logging
import os
import shutil as _sh
import subprocess as _sp
import wave
from dataclasses import dataclass, field
from pathlib import Path

from src.engines.echomimic_engine import EchoMimicEngine
from src.engines.flux_engine import FluxEngine
from src.engines.manager import EngineManager
from src.engines.voice_engine import VoiceEngine
# WanEngineはsubprocess方式に移行したため直接importしない
# (wan_engine.pyはtorchをimportするため、main venvにtorchがない環境で失敗する)
from src.pipeline.compositor import Caption, CompositeConfig, Compositor

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# サーバー別パス設定（.env で上書き可能）
# ──────────────────────────────────────────────────────────────

# Wav2Lip 設定
WAV2LIP_PYTHON = os.getenv(
    "WAV2LIP_PYTHON",
    "/mnt/models/Wav2Lip/venv/bin/python",   # cocoro-server-01 デフォルト
)
WAV2LIP_DIR = os.getenv(
    "WAV2LIP_DIR",
    "/mnt/models/Wav2Lip",
)
WAV2LIP_CHECKPOINT = os.path.join(WAV2LIP_DIR, "checkpoints/wav2lip_gan.pth")
WAV2LIP_INFERENCE  = os.path.join(WAV2LIP_DIR, "inference.py")

# Wan2.1 設定
WAN2_PYTHON = os.getenv(
    "WAN2_PYTHON",
    "/data/venv/wan2/bin/python",            # cocoro-render-01 デフォルト
)
WAN2_MODEL_PATH = os.getenv(
    "WAN2_MODEL_PATH",
    "/data/models/Wan2.1/I2V-14B-480P",
)
WAN2_SCRIPT = "/home/cocoro-influencer/scripts/generate_wan_video.py"

logger.info(
    "Orchestrator設定: WAV2LIP_PYTHON=%s WAV2LIP_DIR=%s WAN2_PYTHON=%s WAN2_MODEL_PATH=%s",
    WAV2LIP_PYTHON, WAV2LIP_DIR, WAN2_PYTHON, WAN2_MODEL_PATH,
)



@dataclass
class ScriptScene:
    """台本の1シーン定義"""

    text: str                           # ナレーションテキスト
    scene_type: str = "talking_head"    # "talking_head" | "cinematic"
    cinematic_prompt: str = ""
    pose: str = "neutral"
    camera_angle: str = "upper_body"
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


# pose → 使用する InstantID 生成済み画像のマッピング
_POSE_IMAGE_MAP_UPPER: dict[str, str] = {
    "neutral": "avatar_neutral_upper.png",
    "greeting": "avatar_greeting_full.png",
    "walk": "avatar_walking_full.png",
    "fullbody": "avatar_fullbody_ref_gen.png",
}
_POSE_IMAGE_MAP_FULL: dict[str, str] = {
    "neutral": "avatar_fullbody_ref_gen.png",
    "greeting": "avatar_greeting_full.png",
    "walk": "avatar_walking_full.png",
    "fullbody": "avatar_fullbody_ref_gen.png",
}

# pose → Kling プロンプト補足
_POSE_PROMPT_MAP: dict[str, str] = {
    "neutral": "natural pose, looking at camera",
    "greeting": "waving hand, greeting gesture, friendly smile",
    "walk": "walking naturally, dynamic movement",
    "fullbody": "full body, standing naturally",
}


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
        # WanEngine は subprocess 方式に移行したため登録しない
        self._manager.register("echomimic", EchoMimicEngine())
        self._manager.register("voice", VoiceEngine(config.voicevox_url, config.speaker_id))

    # ──────────────────────────────────────────────────────────
    # 内部ヘルパー
    # ──────────────────────────────────────────────────────────

    def _select_pose_image(self, scene: ScriptScene, avatar_path: Path) -> str:
        """pose と camera_angle から使用する画像パスを返す"""
        if scene.camera_angle == "full_body":
            img_name = _POSE_IMAGE_MAP_FULL.get(scene.pose, "avatar.png")
        else:
            img_name = _POSE_IMAGE_MAP_UPPER.get(scene.pose, "avatar.png")

        pose_img_path = self._config.output_dir / img_name
        if pose_img_path.exists():
            logger.info("Pose画像使用: %s", pose_img_path)
            return str(pose_img_path.resolve())
        logger.info("デフォルト画像使用: %s", avatar_path)
        return str(avatar_path.resolve())

    def _build_kling_prompt(self, scene: ScriptScene) -> str:
        """シーン情報から Kling AI プロンプトを構築する"""
        pose_desc = _POSE_PROMPT_MAP.get(scene.pose, "natural pose")
        base = scene.cinematic_prompt or "studio lighting, professional setting"
        if scene.appearance_prompt:
            base = f"{scene.appearance_prompt}, {base}"
        return f"{pose_desc}, {base}, talking head video"

    async def _generate_scene_clip(
        self,
        scene: ScriptScene,
        scene_index: int,
        audio_path: Path,
        audio_duration: float,
        avatar_path: Path,
    ) -> Path:
        """1シーン分のKling動画生成 + Wav2Lipリップシンクを実行する。

        フルパイプラインと単体生成の両方から呼び出される共通処理。

        Args:
            scene: シーン定義
            scene_index: ファイル番号 (000, 001, ...)
            audio_path: 音声WAVファイルパス
            audio_duration: 音声長（秒）
            avatar_path: ベースアバター画像パス（フォールバック用）

        Returns:
            生成したクリップのパス
        """
        import httpx as _httpx
        from src.modules.video_gen.kling import KlingAPIClient

        clip_path = self._config.output_dir / f"scene_{scene_index:03d}_clip.mp4"

        if clip_path.exists():
            logger.info("Orchestrator: クリップ既存スキップ %s", clip_path)
            return clip_path

        image_data_url = self._select_pose_image(scene, avatar_path)
        kling_prompt = self._build_kling_prompt(scene)
        logger.info("Orchestrator: Kling prompt: %s", kling_prompt)

        # camera_angle に応じてアスペクト比を決定
        # 全身 → 9:16 (縦長ポートレート) で顔崩れを防ぐ
        # 上半身・顔UP も shorts 縦長フォーマットに統一
        aspect_ratio_map = {
            "full_body": "9:16",
            "upper_body": "9:16",
            "close_up": "9:16",
        }
        aspect_ratio = aspect_ratio_map.get(scene.camera_angle, "9:16")
        logger.info("Orchestrator: Kling aspect_ratio=%s (camera_angle=%s)", aspect_ratio, scene.camera_angle)

        # Kling I2V タスク送信・待機
        kling = KlingAPIClient()
        task_id = await kling.submit_i2v_task(
            image_url=image_data_url,
            prompt=kling_prompt,
            duration=5 if audio_duration <= 5 else 10,
            aspect_ratio=aspect_ratio,
        )
        video_url = await kling.wait_for_task(task_id)

        # WAV → MP3 変換（Wav2Lip用）
        mp3_path = audio_path.with_suffix(".mp3")
        _sp.run(["ffmpeg", "-i", str(audio_path), str(mp3_path), "-y"], check=True)

        # Kling 動画ダウンロード & H264 再エンコード
        kling_raw_path = clip_path.with_name(clip_path.stem + "_kling_raw.mp4")
        kling_video_path = clip_path.with_name(clip_path.stem + "_kling.mp4")
        async with _httpx.AsyncClient(timeout=120.0) as hc:
            r = await hc.get(video_url)
            kling_raw_path.write_bytes(r.content)
        _sp.run([
            "ffmpeg", "-i", str(kling_raw_path),
            "-c:v", "libx264", "-c:a", "aac",
            "-movflags", "+faststart",
            str(kling_video_path), "-y",
        ], check=True)

        # Wav2Lip リップシンク
        lipsync_path = clip_path.with_name(clip_path.stem + "_lipsync.mp4")
        if scene.camera_angle == "full_body":
            # 全身動画: 顔クロップ → Wav2Lip → 元サイズにオーバーレイ
            logger.info("Orchestrator: 全身シーン Wav2Lip (顔クロップ方式) 試行")
            try:
                w2l_result = _sp.run([
                    WAV2LIP_PYTHON,
                    "/home/cocoro-influencer/scripts/wav2lip_fullbody.py",
                    "--face", str(kling_video_path),
                    "--audio", str(audio_path),
                    "--outfile", str(lipsync_path),
                    "--padding", "100",
                    "--lipsync_scale", "720",
                ], capture_output=True, text=True, cwd=WAV2LIP_DIR)

                if w2l_result.returncode == 0 and lipsync_path.exists():
                    _sh.copy(str(lipsync_path), str(clip_path))
                    logger.info("Orchestrator: 全身Wav2Lip完了 %s", clip_path)
                else:
                    logger.warning(
                        "Orchestrator: 全身Wav2Lip失敗(code=%d) → Kling動画を使用\n%s",
                        w2l_result.returncode, w2l_result.stderr[-300:],
                    )
                    _sh.copy(str(kling_video_path), str(clip_path))
            except Exception as exc:
                logger.warning("Orchestrator: 全身Wav2Lipエラー(%s) → Kling動画を使用", exc)
                _sh.copy(str(kling_video_path), str(clip_path))
        else:
            try:
                _sp.run([
                    WAV2LIP_PYTHON,
                    WAV2LIP_INFERENCE,
                    "--checkpoint_path", WAV2LIP_CHECKPOINT,
                    "--face", str(kling_video_path),
                    "--audio", str(audio_path),
                    "--outfile", str(lipsync_path),
                ], check=True, cwd=WAV2LIP_DIR)
                if lipsync_path.exists():
                    _sh.copy(str(lipsync_path), str(clip_path))
                    logger.info("Orchestrator: Wav2Lip完了 %s", clip_path)
                else:
                    logger.warning("Orchestrator: Wav2Lip出力なし、Kling動画を使用")
                    _sh.copy(str(kling_video_path), str(clip_path))
            except Exception as exc:
                logger.warning("Orchestrator: Wav2Lipエラー(%s)、Kling動画を使用", exc)
                _sh.copy(str(kling_video_path), str(clip_path))

        return clip_path

    async def _generate_cinematic_clip(
        self,
        scene: "ScriptScene",
        scene_index: int,
        audio_path: Path,
        audio_duration: float,
        avatar_path: Path,
    ) -> Path:
        """cineマティックシーンをWan2.1ローカル推論で生成する

        WAN2_PYTHON / WAN2_MODEL_PATH 環境変数で設定されたパスを使用。
        モデルが未配備またはエラー時はKling AI にフォールバックする。

        Args:
            scene: シーン定義
            scene_index: シーンのインデックス
            audio_path: 音声Wavファイルパス
            audio_duration: 音声長(秒)
            avatar_path: アバター画像パス

        Returns:
            生成した動画クリップのパス
        """
        from pathlib import Path as _Path

        config = self._config
        clip_path = config.output_dir / f"scene_{scene_index:03d}_clip.mp4"

        # Wan2.1モデルが配備済みか確認
        wan_model = _Path(WAN2_MODEL_PATH)
        wan_python = _Path(WAN2_PYTHON)
        model_ready = wan_model.exists() and wan_python.exists()

        if not model_ready:
            logger.warning(
                "Wan2.1未配備 (model=%s, python=%s) → Kling AI フォールバック",
                WAN2_MODEL_PATH, WAN2_PYTHON,
            )
            return await self._generate_scene_clip(
                scene=scene, scene_index=scene_index,
                audio_path=audio_path, audio_duration=audio_duration,
                avatar_path=avatar_path,
            )

        # 入力画像選択（通常のpose選択と同じロジック）
        image_path = self._select_pose_image(scene, avatar_path)

        # 音声長に合わせたフレーム数を計算 (Wan2.1 は 16fps)
        # 最低4秒 (97フレーム)、最大8秒 (193フレーム)
        fps = 16
        target_frames = max(97, min(193, int(audio_duration * fps) + 1))
        # 奇数フレームにアライメント（Wan2.1の要件）
        if target_frames % 2 == 0:
            target_frames += 1

        prompt_parts = [
            scene.cinematic_prompt or "professional video, smooth camera movement",
            "high quality, cinematic, photorealistic",
        ]
        if scene.appearance_prompt:
            prompt_parts.insert(0, scene.appearance_prompt)
        full_prompt = ", ".join(p for p in prompt_parts if p)

        logger.info(
            "Orchestrator: Wan2.1 シネマティック生成 (frames=%d, %.1f秒): %s",
            target_frames, audio_duration, full_prompt[:60],
        )

        try:
            wan_result = _sp.run([
                str(WAN2_PYTHON),
                WAN2_SCRIPT,
                "--image",      image_path,
                "--prompt",     full_prompt,
                "--outfile",    str(clip_path),
                "--model",      str(WAN2_MODEL_PATH),
                "--num_frames", str(target_frames),
                "--steps",      "30",
                "--width",      "480",
                "--height",     "832",   # 9:16縦動画
            ], capture_output=True, text=True, timeout=3600)

            if wan_result.returncode == 0 and clip_path.exists():
                logger.info("Wan2.1シネマティック完了: %s", clip_path)
                return clip_path
            else:
                logger.warning(
                    "Wan2.1失敗 (code=%d) → Kling フォールバック\n%s",
                    wan_result.returncode, wan_result.stderr[-300:],
                )
        except Exception as exc:
            logger.warning("Wan2.1エラー (%s) → Kling フォールバック", exc)

        # フォールバック: Kling AI
        return await self._generate_scene_clip(
            scene=scene, scene_index=scene_index,
            audio_path=audio_path, audio_duration=audio_duration,
            avatar_path=avatar_path,
        )

    # ──────────────────────────────────────────────────────────
    # 公開メソッド
    # ──────────────────────────────────────────────────────────

    async def run_single_scene(
        self,
        scene: ScriptScene,
        scene_index: int = 0,
    ) -> Path:
        """1シーンのみ動画生成（8秒単体生成モード）

        アバター生成をスキップし、既存の InstantID 生成済み画像を使用。
        音声 → Kling AI → Wav2Lip のみ実行するため高速。

        Args:
            scene: シーン定義
            scene_index: 出力ファイルの番号（scene_000_clip.mp4 等）

        Returns:
            生成したクリップのパス
        """
        config = self._config
        config.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Orchestrator: 単体シーン生成開始 index=%d pose=%s angle=%s",
            scene_index, scene.pose, scene.camera_angle,
        )

        # フォールバック用アバター画像
        avatar_path = config.output_dir / "avatar.png"

        # Step 1: 音声生成
        audio_path = config.output_dir / f"scene_{scene_index:03d}_voice.wav"
        if not audio_path.exists():
            voice_engine = self._manager.get("voice")
            voice_engine.generate(text=scene.text, output_path=audio_path)

        # 音声長取得
        with wave.open(str(audio_path), "rb") as wf:
            audio_duration = wf.getnframes() / wf.getframerate()

        # Step 2: 動画生成（Kling + Wav2Lip）
        clip_path = await self._generate_scene_clip(
            scene=scene,
            scene_index=scene_index,
            audio_path=audio_path,
            audio_duration=audio_duration,
            avatar_path=avatar_path,
        )

        self._manager.unload_all()
        logger.info("Orchestrator: 単体シーン完了 → %s", clip_path)
        return clip_path

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
            logger.info("Orchestrator: [1/4] アバター画像は既存 (%s)", avatar_path)

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
            with wave.open(str(audio_path), "rb") as wf:
                audio_duration = wf.getnframes() / wf.getframerate()

            # Step 3: 動画生成
            clip_path = config.output_dir / f"scene_{i:03d}_clip.mp4"
            if not clip_path.exists():
                if scene.scene_type == "cinematic":
                    # Wan2.1ローカル推論 (subprocess) またはKling AIにフォールバック
                    clip_path = await self._generate_cinematic_clip(
                        scene=scene,
                        scene_index=i,
                        audio_path=audio_path,
                        audio_duration=audio_duration,
                        avatar_path=avatar_path,
                    )
                else:
                    # talking_head: Kling AI I2V → Wav2Lip リップシンク
                    clip_path = await self._generate_scene_clip(
                        scene=scene,
                        scene_index=i,
                        audio_path=audio_path,
                        audio_duration=audio_duration,
                        avatar_path=avatar_path,
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
