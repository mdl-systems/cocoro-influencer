"""orchestrator.py: パイプライン全体制御モジュール

台本YAML → 音声 → 画像 → 動画 → 合成 の
フルパイプラインを順番に実行する。

単体シーン生成 (run_single_scene) も提供。

## サーバー環境変数設定 (config/.env)
  WAV2LIP_PYTHON  : Wav2Lip venv の python パス
  WAV2LIP_DIR     : Wav2Lip リポジトリのルートディレクトリ
  WAN2_PYTHON     : Wan2.1 venv の python パス
  WAN2_MODEL_PATH : Wan2.1 モデルのローカルパス
  INSTANTID_PYTHON: InstantID venv の python パス
  INSTANTID_DIR   : InstantID リポジトリのルートディレクトリ

## デフォルト値 (cocoro-render-01用)
  WAV2LIP_PYTHON  = /data/models/Wav2Lip/venv/bin/python
  WAV2LIP_DIR     = /data/models/Wav2Lip
  WAN2_PYTHON     = /data/venv/wan2/bin/python
  WAN2_MODEL_PATH = /data/models/Wan2.1/I2V-14B-480P
  INSTANTID_PYTHON= /data/models/InstantID/venv/bin/python
  INSTANTID_DIR   = /data/models/InstantID
"""

import logging
import os
import shutil as _sh
import subprocess as _sp
import wave
from collections.abc import Awaitable, Callable
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
    "/data/models/Wav2Lip/venv/bin/python",   # cocoro-render-01 デフォルト
)
WAV2LIP_DIR = os.getenv(
    "WAV2LIP_DIR",
    "/data/models/Wav2Lip",
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

# InstantID 設定
INSTANTID_PYTHON = os.getenv(
    "INSTANTID_PYTHON",
    "/data/models/InstantID/venv/bin/python",  # cocoro-render-01 デフォルト
)
INSTANTID_DIR = os.getenv(
    "INSTANTID_DIR",
    "/data/models/InstantID",
)

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
    output_format: str = "shorts"              # 出力フォーマット (shorts=720x1280縦動画/Wan2.1適合, youtube=1920x1080横)
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


    # ────────────────────────────────────────────────────────
    # 内部ヘルパー
    # ────────────────────────────────────────────────────────

    def _select_pose_image(self, scene: ScriptScene, avatar_path: Path) -> str:
        """ポーズと camera_angle から使用する画像パスを返す.

        InstantID発螋済み画像が存在する場合はそちらを優先。
        ない場合は avatar_path (アップロード者の元写真) からフォールバック。
        """
        if scene.camera_angle == "full_body":
            img_name = _POSE_IMAGE_MAP_FULL.get(scene.pose, "avatar.png")
        else:
            img_name = _POSE_IMAGE_MAP_UPPER.get(scene.pose, "avatar.png")

        pose_img_path = self._config.output_dir / img_name
        if pose_img_path.exists():
            logger.info("✅ InstantIDポーズ画像使用: %s", pose_img_path.name)
            return str(pose_img_path.resolve())

        # インスタントID画像が存在しない場合はウォーニングを出してフォールバック
        available = [f.name for f in self._config.output_dir.glob("avatar_*.png")]
        logger.warning(
            "⚠️ InstantID画像 '%s' が未生成 → フォールバック: %s "
            "(利用可能なインスタントID画像: %s)",
            img_name, avatar_path.name, available or "なし",
        )
        return str(avatar_path.resolve())

    def _build_kling_prompt(self, scene: ScriptScene) -> str:
        """シーン情報からプロンプトを構築する"""
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
        on_progress: "Callable[[int, str], Awaitable[None]] | None" = None,
        progress_start: int = 20,
        progress_end: int = 85,
    ) -> Path:
        """talking_head シーンを Wan2.1 + Wav2Lip で生成する（完全ローカル・非同期）

        Args:
            scene: シーン定義
            scene_index: ファイル番号 (000, 001, ...)
            audio_path: 音声WAVファイルパス
            audio_duration: 音声長（秒）
            avatar_path: ベースアバター画像パス（フォールバック用）
            on_progress: 進捗コールバック (progress%, message)
            progress_start: 進捗開始値 (%)
            progress_end: 進捗終了値 (%)

        Returns:
            生成したクリップのパス
        """
        from pathlib import Path as _Path

        clip_path = self._config.output_dir / f"scene_{scene_index:03d}_clip.mp4"

        if clip_path.exists():
            logger.info("Orchestrator: クリップ既存スキップ %s", clip_path)
            return clip_path

        # 入力画像選択
        image_path = self._select_pose_image(scene, avatar_path)

        # 音声長に合わせてフレーム数計算 (16fps)
        # Wan2.1 は 4k+1 フレームのみ有効 (33, 37, 41, ..., 65, ..., 105, 109, ...)
        fps = 16
        raw_frames = int(audio_duration * fps) + 1
        k = max(8, (raw_frames - 1) // 4)  # 最低33フレーム (k≥8)
        target_frames = 4 * k + 1
        # 上限 = 129 (8秒@16fps相当の 4k+1)
        if target_frames > 129:
            target_frames = 129  # 129 = 4*32+1
        # 少し短い場合は切り上げ（音声に合わせる）
        if target_frames < raw_frames and target_frames + 4 <= 129:
            target_frames += 4

        # talking_head 用プロンプト（自然な表情・微動）
        pose_desc = _POSE_PROMPT_MAP.get(scene.pose, "natural pose")
        wan_prompt = (
            f"{pose_desc}, subtle head movement, natural blinking, talking, "
            "studio lighting, professional setting, high quality"
        )
        logger.info(
            "Orchestrator: Wan2.1 talking_head生成 (frames=%d, %.1f秒): %s",
            target_frames, audio_duration, wan_prompt[:60],
        )

        # Wan2.1 サブプロセス実行
        # PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True でVRAM断片化OOMを防ぐ
        wan_raw_path = clip_path.with_name(clip_path.stem + "_wan_raw.mp4")
        wan_ok = False
        wan_env = {**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
        wan_cmd = [
            str(WAN2_PYTHON),
            WAN2_SCRIPT,
            "--image",      image_path,
            "--prompt",     wan_prompt,
            "--outfile",    str(wan_raw_path),
            "--model",      str(WAN2_MODEL_PATH),
            "--num_frames", str(target_frames),
            "--steps",      "20",
            "--width",      "480",
            "--height",     "832",
        ]

        for attempt in range(2):  # OOM時は1回リトライ
            try:
                if attempt > 0:
                    logger.info("Orchestrator: Wan2.1 リトライ %d/2 (60秒待機後)", attempt + 1)
                    import asyncio as _aio
                    await _aio.sleep(60)

                # 非同期サブプロセスで実行し、stdout WAN_STEP: をリアルタイムで進捗報告
                returncode, stderr_tail = await self._run_wan_subprocess_async(
                    cmd=wan_cmd,
                    env=wan_env,
                    num_steps=20,  # talking_head は steps=20
                    progress_start=progress_start,
                    progress_end=progress_end,
                    on_progress=on_progress,
                )

                if returncode == 0 and wan_raw_path.exists():
                    logger.info("Orchestrator: Wan2.1完了 → Wav2Lip適用")
                    wan_ok = True
                    break
                else:
                    logger.warning(
                        "Orchestrator: Wan2.1 talking_head失敗 (code=%d, attempt=%d)\n%s",
                        returncode, attempt + 1, stderr_tail,
                    )
                    # OOMでなければリトライ不要
                    if "out of memory" not in stderr_tail.lower():
                        break
            except Exception as exc:
                logger.warning("Orchestrator: Wan2.1エラー (attempt=%d, %s)", attempt + 1, exc)
                break


        if not wan_ok:
            # フォールバック: FFmpegで静止画から音声長ぶんのビデオを生成
            # ※ PNG をそのまま .mp4 にコピーするとコンポジターが壊れるため
            logger.warning("Orchestrator: Wan2.1失敗 → 静止画フォールバックビデオ生成 (%.1f秒)", audio_duration)
            try:
                fallback_result = _sp.run([
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", image_path,
                    "-c:v", "libx264",
                    "-t", str(max(audio_duration, 1.0)),
                    "-pix_fmt", "yuv420p",
                    "-vf", "scale=480:832:force_original_aspect_ratio=decrease,"
                           "pad=480:832:(ow-iw)/2:(oh-ih)/2:color=black",
                    "-r", "16",
                    str(clip_path),
                ], capture_output=True, text=True, timeout=120)
                if fallback_result.returncode != 0:
                    raise RuntimeError(fallback_result.stderr[-200:])
                logger.info("Orchestrator: フォールバックビデオ生成完了 → %s", clip_path)
            except Exception as fb_exc:
                logger.error("Orchestrator: フォールバックビデオ生成失敗 (%s) → 画像コピーで代替", fb_exc)
                _sh.copy(image_path, str(clip_path))
            return clip_path

        # Wav2Lip リップシンク（全身顔クロップ方式）
        lipsync_path = clip_path.with_name(clip_path.stem + "_lipsync.mp4")
        try:
            w2l_result = _sp.run([
                WAV2LIP_PYTHON,
                "/home/cocoro-influencer/scripts/wav2lip_fullbody.py",
                "--face",    str(wan_raw_path),
                "--audio",   str(audio_path),
                "--outfile", str(lipsync_path),
            ], capture_output=True, text=True, cwd=WAV2LIP_DIR)

            if w2l_result.returncode == 0 and lipsync_path.exists():
                _sh.copy(str(lipsync_path), str(clip_path))
                logger.info("Orchestrator: Wav2Lip完了 → %s", clip_path)
            else:
                logger.warning(
                    "Orchestrator: Wav2Lip失敗 → Wan2.1動画を使用\n%s",
                    w2l_result.stderr[-200:],
                )
                _sh.copy(str(wan_raw_path), str(clip_path))
        except Exception as exc:
            logger.warning("Orchestrator: Wav2Lipエラー(%s) → Wan2.1動画を使用", exc)
            _sh.copy(str(wan_raw_path), str(clip_path))

        return clip_path

    async def _generate_kling_clip(
        self,
        scene: ScriptScene,
        scene_index: int,
        audio_path: Path,
        audio_duration: float,
        avatar_path: Path,
    ) -> Path:
        """[将来用] Kling AI I2V + Wav2Lip でクリップ生成（APIクレジット必要）"""
        import httpx as _httpx
        from src.modules.video_gen.kling import KlingAPIClient

        clip_path = self._config.output_dir / f"scene_{scene_index:03d}_clip.mp4"

        if clip_path.exists():
            logger.info("Orchestrator: クリップ既存スキップ %s", clip_path)
            return clip_path

        image_data_url = self._select_pose_image(scene, avatar_path)
        kling_prompt = self._build_kling_prompt(scene)
        logger.info("Orchestrator: Kling prompt: %s", kling_prompt)

        aspect_ratio_map = {
            "full_body": "9:16",
            "upper_body": "9:16",
            "close_up": "9:16",
        }
        aspect_ratio = aspect_ratio_map.get(scene.camera_angle, "9:16")

        kling = KlingAPIClient()
        task_id = await kling.submit_i2v_task(
            image_url=image_data_url,
            prompt=kling_prompt,
            duration=5 if audio_duration <= 5 else 10,
            aspect_ratio=aspect_ratio,
        )
        video_url = await kling.wait_for_task(task_id)

        mp3_path = audio_path.with_suffix(".mp3")
        _sp.run(["ffmpeg", "-i", str(audio_path), str(mp3_path), "-y"], check=True)

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

        lipsync_path = clip_path.with_name(clip_path.stem + "_lipsync.mp4")
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

        return clip_path

    async def _generate_cinematic_clip(
        self,
        scene: "ScriptScene",
        scene_index: int,
        audio_path: Path,
        audio_duration: float,
        avatar_path: Path,
        on_progress: "Callable[[int, str], Awaitable[None]] | None" = None,
        progress_start: int = 20,
        progress_end: int = 85,
    ) -> Path:
        """Wan2.1シネマティックシーンを生成する

        WAN2_PYTHON / WAN2_MODEL_PATH 環境変数で設定されたパスを使用。
        on_progress を受け取ってWan2.1ステップ毎に進捗を報告する。
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
                "Wan2.1未配備 (model=%s, python=%s) → talking_head方式にフォールバック",
                WAN2_MODEL_PATH, WAN2_PYTHON,
            )
            return await self._generate_scene_clip(
                scene=scene, scene_index=scene_index,
                audio_path=audio_path, audio_duration=audio_duration,
                avatar_path=avatar_path,
                on_progress=on_progress,
                progress_start=progress_start, progress_end=progress_end,
            )

        # 入力画像選択
        image_path = self._select_pose_image(scene, avatar_path)

        # 音声長に合わせたフレーム数を計算 (16fps)
        # Wan2.1 は 4k+1 フレームのみ有効 (33, 37, ..., 97, 101, ..., 189, 193)
        fps = 16
        raw_frames = int(audio_duration * fps) + 1
        k = max(24, (raw_frames - 1) // 4)  # 最低97フレーム (k≥24)
        target_frames = 4 * k + 1
        if target_frames > 193:
            target_frames = 193  # 193 = 4*48+1
        if target_frames < raw_frames and target_frames + 4 <= 193:
            target_frames += 4

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

        wan_env = {**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
        wan_cmd = [
            str(WAN2_PYTHON),
            WAN2_SCRIPT,
            "--image",      str(image_path),
            "--prompt",     full_prompt,
            "--outfile",    str(clip_path),
            "--model",      str(WAN2_MODEL_PATH),
            "--num_frames", str(target_frames),
            "--steps",      "30",
            "--width",      "480",
            "--height",     "832",
        ]

        try:
            returncode, stderr_tail = await self._run_wan_subprocess_async(
                cmd=wan_cmd,
                env=wan_env,
                num_steps=30,
                progress_start=progress_start,
                progress_end=progress_end,
                on_progress=on_progress,
            )

            if returncode == 0 and clip_path.exists():
                logger.info("Wan2.1シネマティック完了: %s", clip_path)
                return clip_path
            else:
                logger.warning(
                    "Wan2.1失敗 (code=%d) → talking_head方式にフォールバック\n%s",
                    returncode, stderr_tail,
                )
        except Exception as exc:
            logger.warning("Wan2.1エラー (%s) → talking_head方式にフォールバック", exc)

        # フォールバック: talking_head方式 (Wan2.1)
        return await self._generate_scene_clip(
            scene=scene, scene_index=scene_index,
            audio_path=audio_path, audio_duration=audio_duration,
            avatar_path=avatar_path,
            on_progress=on_progress,
            progress_start=progress_start, progress_end=progress_end,
        )

    # ──────────────────────────────────────────────────────────
    # 内部ヘルパー: Wan2.1 非同期サブプロセス実行
    # ──────────────────────────────────────────────────────────

    async def _run_wan_subprocess_async(
        self,
        cmd: list[str],
        env: dict,
        num_steps: int,
        progress_start: int,
        progress_end: int,
        on_progress: "Callable[[int, str], Awaitable[None]] | None",
    ) -> "tuple[int, str]":
        """Wan2.1サブプロセスを非同期起動し、stdoutをリアルタイムに読んで進捗を報告する

        generate_wan_video.py が stdout に出力する以下の行をパース:
            WAN_STEP: {current}/{total}  → ステップ進捗を on_progress に変換
            WAN_PHASE: {message}         → フェーズ変化をログ / 進捗更新

        stderrは OOM 検出のために最後30行を保持して返す。

        Returns:
            (returncode, stderr_tail)
        """
        import asyncio as _aio

        proc = await _aio.create_subprocess_exec(
            *cmd,
            stdout=_aio.subprocess.PIPE,
            stderr=_aio.subprocess.PIPE,
            env=env,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None

        stderr_chunks: list[str] = []
        step_pct_range = progress_end - progress_start

        async def _read_stdout() -> None:
            while True:
                line_b = await proc.stdout.readline()  # type: ignore[union-attr]
                if not line_b:
                    break
                line = line_b.decode(errors="replace").rstrip()
                if line.startswith("WAN_STEP:"):
                    try:
                        parts = line.split(":", 1)[1].strip().split("/")
                        current, total = int(parts[0]), int(parts[1])
                        step_frac = current / max(total, 1)
                        pct = progress_start + int(step_pct_range * step_frac)
                        msg = f"Wan2.1 推論ステップ {current}/{total}..."
                        if on_progress:
                            await on_progress(pct, msg)
                    except Exception:
                        pass
                elif line.startswith("WAN_PHASE:"):
                    phase = line.split(":", 1)[1].strip()
                    logger.info("Wan2.1フェーズ: %s", phase)
                    if on_progress and "推論開始" in phase:
                        await on_progress(progress_start, f"Wan2.1 {phase}...")
                else:
                    logger.debug("wan_stdout: %s", line)

        async def _read_stderr() -> None:
            while True:
                line_b = await proc.stderr.readline()  # type: ignore[union-attr]
                if not line_b:
                    break
                line = line_b.decode(errors="replace").rstrip()
                stderr_chunks.append(line)
                logger.debug("wan_stderr: %s", line)

        await _aio.gather(_read_stdout(), _read_stderr())
        await proc.wait()

        returncode = proc.returncode or 0
        stderr_tail = "\n".join(stderr_chunks[-30:])
        return returncode, stderr_tail

    # ──────────────────────────────────────────────────────────
    # 公開メソッド
    # ──────────────────────────────────────────────────────────

    async def run_single_scene(
        self,
        scene: ScriptScene,
        scene_index: int = 0,
        on_progress: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> Path:
        """1シーンのみ動画生成（8秒単体生成モード）

        アバター生成をスキップし、既存の InstantID 生成済み画像を使用。
        音声 → Wan2.1 → Wav2Lip のみ実行して高速。

        Args:
            scene: シーン定義
            scene_index: 出力ファイルの番号（scene_000_clip.mp4 等）
            on_progress: 進捗コールバック (progress%, message)

        Returns:
            生成したクリップのパス
        """
        config = self._config
        config.output_dir.mkdir(parents=True, exist_ok=True)

        async def _progress(pct: int, msg: str) -> None:
            logger.info("Orchestrator単体: [%d%%] %s", pct, msg)
            if on_progress:
                try:
                    await on_progress(pct, msg)
                except Exception as _pe:
                    logger.warning("progress callback error: %s", _pe)

        logger.info(
            "Orchestrator: 単体シーン生成開始 index=%d pose=%s angle=%s",
            scene_index, scene.pose, scene.camera_angle,
        )

        # フォールバック用アバター画像
        avatar_path = config.output_dir / "avatar.png"

        # Step 1: 音声生成
        audio_path = config.output_dir / f"scene_{scene_index:03d}_voice.wav"
        if not audio_path.exists():
            await _progress(10, "音声合成中 (Style-Bert-VITS2)...")
            voice_engine = self._manager.get("voice")
            voice_engine.generate(text=scene.text, output_path=audio_path)
        await _progress(30, "音声合成完了 → Wan2.1動画生成開始...")

        # 音声長取得
        with wave.open(str(audio_path), "rb") as wf:
            audio_duration = wf.getnframes() / wf.getframerate()

        # Step 2: 動画生成（Wan2.1 + Wav2Lip）
        # on_progress を伝播させ、30%→95% の範囲で進捗を報告する
        clip_path = await self._generate_scene_clip(
            scene=scene,
            scene_index=scene_index,
            audio_path=audio_path,
            audio_duration=audio_duration,
            avatar_path=avatar_path,
            on_progress=on_progress,
            progress_start=35,
            progress_end=95,
        )
        await _progress(98, "Wav2Lipリップシンク完了 → 出力準備中...")

        self._manager.unload_all()
        logger.info("Orchestrator: 単体シーン完了 → %s", clip_path)
        return clip_path

    async def run(
        self,
        on_progress: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> Path:
        """フルパイプラインを実行する

        Returns:
            生成した最終動画ファイルのパス
        """
        config = self._config
        config.output_dir.mkdir(parents=True, exist_ok=True)

        async def _progress(pct: int, msg: str) -> None:
            """進捗コールバックを安全に呼び出す"""
            logger.info("Orchestrator: [%d%%] %s", pct, msg)
            if on_progress:
                try:
                    await on_progress(pct, msg)
                except Exception as _pe:
                    logger.warning("progress callback error: %s", _pe)

        await _progress(5, "パイプライン開始")

        # Step 1: アバター画像確認/生成
        avatar_path = config.output_dir / "avatar.png"
        if not avatar_path.exists():
            if not config.avatar_prompt:
                # アップロードなし・プロンプトなし: 明確なエラーで失敗させる
                raise RuntimeError(
                    "avatar.png が存在せず、avatar_prompt も指定されていません。"
                    "顔写真をアップロードするか、プロンプトを指定してください。"
                )
            await _progress(8, "アバター画像生成中 (FLUX)...")
            logger.info("Orchestrator: [1/4] アバター画像生成 (プロンプト: %s...)", config.avatar_prompt[:40])
            engine = self._manager.get("flux")
            engine.generate(
                prompt=config.avatar_prompt,
                output_path=avatar_path,
                lora_path=config.lora_path,
                seed=config.avatar_seed,
            )
        else:
            logger.info("Orchestrator: [1/4] アバター画像は既存 (%s, %.1fKB)",
                        avatar_path.name, avatar_path.stat().st_size / 1024)

        await _progress(10, "音声合成中...")

        clip_paths: list[Path] = []
        captions: list[Caption] = []
        elapsed: float = 0.0

        # Step 2 & 3: シーンごとに音声→動画生成
        total_scenes = len(config.scenes)
        for i, scene in enumerate(config.scenes):
            logger.info(
                "Orchestrator: シーン %d/%d (type=%s)",
                i + 1, total_scenes, scene.scene_type,
            )
            # シーン別進捗: 音声10%〜動画完了85% の範囲で均等配分
            scene_base = 10 + int(75 * i / total_scenes)
            scene_end  = 10 + int(75 * (i + 1) / total_scenes)

            # Step 2: 音声生成
            audio_path = config.output_dir / f"scene_{i:03d}_voice.wav"
            if not audio_path.exists():
                await _progress(scene_base + 2, f"音声合成中... ({i+1}/{total_scenes})")
                voice_engine = self._manager.get("voice")
                voice_engine.generate(text=scene.text, output_path=audio_path)

            # 音声長を取得
            with wave.open(str(audio_path), "rb") as wf:
                audio_duration = wf.getnframes() / wf.getframerate()

            # Step 3: 動画生成 (on_progress を伝播して進捗をリアルタイム更新)
            clip_path = config.output_dir / f"scene_{i:03d}_clip.mp4"
            if not clip_path.exists():
                await _progress(scene_base + 5, f"動画生成中 (Wan2.1)... ({i+1}/{total_scenes})")
                if scene.scene_type == "cinematic":
                    clip_path = await self._generate_cinematic_clip(
                        scene=scene,
                        scene_index=i,
                        audio_path=audio_path,
                        audio_duration=audio_duration,
                        avatar_path=avatar_path,
                        on_progress=on_progress,
                        progress_start=scene_base + 5,
                        progress_end=scene_end,
                    )
                else:
                    clip_path = await self._generate_scene_clip(
                        scene=scene,
                        scene_index=i,
                        audio_path=audio_path,
                        audio_duration=audio_duration,
                        avatar_path=avatar_path,
                        on_progress=on_progress,
                        progress_start=scene_base + 5,
                        progress_end=scene_end,
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
        await _progress(88, "最終動画合成中 (FFmpeg)...")
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
