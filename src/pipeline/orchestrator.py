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

# SadTalker 設定
SADTALKER_PYTHON = os.getenv(
    "SADTALKER_PYTHON",
    "/data/venv/sadtalker/bin/python",
)
SADTALKER_SCRIPT = "/home/cocoro-influencer/scripts/sadtalker_inference.py"
SADTALKER_AVAILABLE = (
    os.path.exists(SADTALKER_PYTHON)
    and os.path.exists("/data/models/SadTalker")
    and (
        Path("/data/models/SadTalker/checkpoints/epoch_20.pth").exists()
        or any(
            Path(f"/data/models/SadTalker/checkpoints/{f}").exists()
            for f in ["SadTalker_V0.0.2_512.safetensors", "SadTalker_V0.0.2_256.safetensors"]
        )
    )
)

# LivePortrait 設定
LIVEPORTRAIT_PYTHON = os.getenv(
    "LIVEPORTRAIT_PYTHON",
    "/data/venv/liveportrait/bin/python",
)
LIVEPORTRAIT_DIR = os.getenv(
    "LIVEPORTRAIT_DIR",
    "/data/models/LivePortrait",
)
LIVEPORTRAIT_SCRIPT = str(Path(LIVEPORTRAIT_DIR) / "inference.py")
# デフォルト駆動動画（最も自然な動き）
LIVEPORTRAIT_DRIVING_DEFAULT = os.getenv(
    "LIVEPORTRAIT_DRIVING",
    str(Path(LIVEPORTRAIT_DIR) / "assets/examples/driving/d0.mp4"),
)
LIVEPORTRAIT_AVAILABLE = (
    os.path.exists(LIVEPORTRAIT_PYTHON)
    and os.path.exists(LIVEPORTRAIT_SCRIPT)
    and os.path.exists(str(Path(LIVEPORTRAIT_DIR) / "pretrained_weights/liveportrait"))
)

logger.info(
    "Orchestrator設定: WAV2LIP_PYTHON=%s WAV2LIP_DIR=%s WAN2_PYTHON=%s WAN2_MODEL_PATH=%s",
    WAV2LIP_PYTHON, WAV2LIP_DIR, WAN2_PYTHON, WAN2_MODEL_PATH,
)
logger.info("SadTalker: %s (Python=%s)", "利用可能" if SADTALKER_AVAILABLE else "未インストール", SADTALKER_PYTHON)
logger.info("LivePortrait: %s (Python=%s)", "利用可能" if LIVEPORTRAIT_AVAILABLE else "未インストール", LIVEPORTRAIT_PYTHON)

# Wan2.2 設定
WAN22_PYTHON  = WAN2_PYTHON  # 同じ venv を使用
WAN22_SCRIPT  = "/data/models/Wan2.2-repo/generate.py"
WAN22_CKPT    = "/data/models/Wan2.2/I2V-A14B"
WAN22_AVAILABLE = (
    os.path.exists(WAN22_PYTHON)
    and os.path.exists(WAN22_SCRIPT)
    and os.path.exists(WAN22_CKPT)
)
logger.info("Wan2.2: %s (ckpt=%s)", "利用可能" if WAN22_AVAILABLE else "未インストール", WAN22_CKPT)

# HunyuanVideo-I2V 設定
HUNYUAN_I2V_PYTHON = WAN2_PYTHON  # 同じ wan2 venv を使用
HUNYUAN_I2V_SCRIPT = "/home/cocoro-influencer/scripts/generate_hunyuan_i2v_video.py"
HUNYUAN_I2V_MODEL  = "/data/models/HunyuanVideo-I2V"
HUNYUAN_I2V_AVAILABLE = (
    os.path.exists(HUNYUAN_I2V_PYTHON)
    and os.path.exists(HUNYUAN_I2V_MODEL)
    and os.path.exists(HUNYUAN_I2V_SCRIPT)
)
logger.info("HunyuanVideo-I2V: %s (model=%s)", "利用可能" if HUNYUAN_I2V_AVAILABLE else "未インストール", HUNYUAN_I2V_MODEL)

def _unload_ollama_models() -> None:
    """OllamaのロードされているモデルをVRAMからアンロードする.

    Wan2.1実行前に呼び出し、Ollama (Qwen2.5:32B等) が占有しているVRAMを解放する。
    Ollama APIに keep_alive=0 を送信することで即座にモデルをアンロードする。
    """
    import urllib.request
    import json as _json
    try:
        # ロード済みモデル一覧を取得
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=3) as resp:
            data = _json.loads(resp.read())
        models = data.get("models", [])
        if not models:
            logger.info("Ollama: ロード済みモデルなし (アンロード不要)")
            return
        for m in models:
            model_name = m.get("name", "")
            # keep_alive=0 で即座にアンロード
            body = _json.dumps({"model": model_name, "keep_alive": 0}).encode()
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as _r:
                pass
            logger.info("Ollama: モデルをVRAMからアンロードしました: %s", model_name)
    except Exception as e:
        logger.warning("Ollamaアンロードスキップ (エラー: %s)", e)



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
    output_format: str = "shorts"              # 出力フォーマット
    flux_model_id: str = "/home/cocoro-influencer/models/flux"  # ローカルFLUX.1-devモデル
    wan_model_id: str = "/data/models/Wan2.1/I2V-14B-480P"        # ローカルWan2.1モデル
    voicevox_url: str = "http://localhost:5000"
    speaker_id: int = 0                        # ③ Style-Bert-VITS2 話者ID
    model_id: int = 0                          # ③ Style-Bert-VITS2 モデルID
    avatar_seed: int | None = None
    enable_subtitles: bool = False             # ① 台本テキストから字幕自動生成
    bgm_volume: float = 0.12                   # ② BGM音量
    # B-1 フォーマット (已存在の output_format を凝用)
    # B-2 トランジション
    transition: str = "none"                   # トランジション種別
    transition_duration: float = 0.5           # トランジション時間 (秒)
    # B-3 ウォーターマーク
    watermark_path: Path | None = None         # ロゴ画像パス
    watermark_position: str = "bottom-right"   # ウォーターマーク位置
    watermark_scale: float = 0.15              # ウォーターマークサイズ比率
    speech_speed: float = 0.50                 # 話速 (1.0=標準, 0.50=ゆっくり50%減)
    use_sadtalker: bool = True                 # True: SadTalkerでtalking_head生成 (False: Wan2.1+Wav2Lip)
    use_liveportrait: bool = False             # True: LivePortrait+Wav2Lipで体の動き生成 (SadTalkerより優先)
    use_wan22: bool = False                    # True: Wan2.2 I2V+Wav2Lip（腕・体の動き最高品質、最優先）
    wan22_guide_scale: float = 7.5            # Wan2.2 キャラクター忠実度 (5〜9、高いほどアバター固定)
    use_hunyuan_i2v: bool = False             # True: HunyuanVideo-I2V（高品質自然動作）
    hunyuan_guidance: float = 6.0             # HunyuanVideo ガイダンススケール
    hunyuan_steps: int = 30                    # HunyuanVideo 推論ステップ数


# pose → 使用する InstantID 生成済み画像のマッピング
_POSE_IMAGE_MAP_UPPER: dict[str, str] = {
    "neutral":    "avatar_neutral_upper.png",
    "talking":    "avatar_neutral_upper.png",
    "greeting":   "avatar_greeting_full.png",
    "presenting": "avatar_greeting_full.png",
    "thinking":   "avatar_neutral_upper.png",
    "walk":       "avatar_walking_full.png",
    "pointing":   "avatar_greeting_full.png",
    "fullbody":   "avatar_fullbody_ref_gen.png",
}
_POSE_IMAGE_MAP_FULL: dict[str, str] = {
    "neutral":    "avatar_fullbody_ref_gen.png",
    "talking":    "avatar_fullbody_ref_gen.png",
    "greeting":   "avatar_greeting_full.png",
    "presenting": "avatar_greeting_full.png",
    "thinking":   "avatar_fullbody_ref_gen.png",
    "walk":       "avatar_walking_full.png",
    "pointing":   "avatar_greeting_full.png",
    "fullbody":   "avatar_fullbody_ref_gen.png",
}

# pose → Kling プロンプト補足
_POSE_PROMPT_MAP: dict[str, str] = {
    "neutral":    "natural pose, looking at camera",
    "talking":    "talking, speaking gesture, expressive face",
    "greeting":   "waving hand, greeting gesture, friendly smile",
    "presenting": "presenting, explaining with hands, confident gesture",
    "thinking":   "thoughtful expression, hand on chin, contemplating",
    "walk":       "walking naturally, dynamic movement",
    "pointing":   "pointing forward, confident gesture, authoritative",
    "fullbody":   "full body, standing naturally",
}

# 全身シーン専用: ポーズごとに動きプロンプトを使い分ける
# (矛盾するワードを混在させると Wan2.1 が動きを無効化する)
_FULL_BODY_MOTION_MAP: dict[str, str] = {
    "neutral":    "professional presenter, natural standing, subtle body sway, breathing",
    "talking":    "talking with natural gestures, expressive body language, arms moving",
    "greeting":   "greeting gesture, waving hand, friendly smile, full body motion",
    "presenting": "presenting with hands, explaining gesture, confident authoritative stance",
    "thinking":   "thoughtful pose, hand on chin, subtle body sway, contemplating",
    "walk":       "walking naturally, fluid gait, smooth stride, whole body moving",
    "pointing":   "pointing forward, confident standing pose, authoritative gesture",
    "fullbody":   "professional presenter, natural standing, subtle body sway",
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
        self._manager.register("voice", VoiceEngine(config.voicevox_url, speaker_id=config.speaker_id))


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

    def _detect_camera_motion(self, scene: "ScriptScene") -> str:
        """cinematic_prompt と pose からカメラ動きを判定する"""
        prompt = (scene.cinematic_prompt or "").lower()
        pose   = (scene.pose or "").lower()

        # --- 明示的な静止 ---
        if any(k in prompt for k in ["static camera", "fixed camera", "no camera"]):
            return "static"

        # --- ズームイン ---
        if any(k in prompt for k in ["zoom in", "ズームイン", "zoom_in", "close up", "closeup"]):
            return "zoom_in"

        # --- ズームアウト ---
        if any(k in prompt for k in ["zoom out", "ズームアウト", "zoom_out", "wide shot"]):
            return "zoom_out"

        # --- パン ---
        if any(k in prompt for k in ["pan left", "左パン", "pan_left"]):
            return "pan_left"
        if any(k in prompt for k in ["pan right", "右パン", "pan_right"]):
            return "pan_right"

        # --- ティルト ---
        if any(k in prompt for k in ["tilt up", "ティルトアップ", "tilt_up"]):
            return "tilt_up"
        if any(k in prompt for k in ["tilt down", "ティルトダウン", "tilt_down"]):
            return "tilt_down"

        # --- その他（smooth motion / orbit / handheld → ゆるやかなズームイン）---
        if any(k in prompt for k in [
            "smooth motion", "cinematic smooth", "orbit", "handheld", "slight shake"
        ]):
            return "zoom_in"

        # --- ポーズデフォルト ---
        if pose in ("greeting", "presenting"):
            return "zoom_in"
        if pose == "walk":
            return "pan_right"

        return "static"

    def _apply_camera_motion(
        self, clip_path: Path, motion: str, duration: float, w: int = 512, h: int = 512
    ) -> None:
        """FFmpeg でカメラモーションを適用する（in-place）"""
        import subprocess as _sp
        if motion == "static" or duration <= 0:
            return
        D = max(1.0, duration)
        scale = 1.25  # 25% 余白でパン/ズーム用
        # FFmpeg crop フィルター: named parameter 形式（x/y は per-frame 評価がデフォルト）
        sw = f"iw*{scale}"
        sh = f"ih*{scale}"
        cw = f"iw/{scale}"
        ch = f"ih/{scale}"
        cx = f"iw*(1-1/{scale})/2"   # 水平中心オフセット（最大値）
        cy = f"ih*(1-1/{scale})/2"   # 垂直中心オフセット（最大値）

        if motion == "zoom_in":
            # 0,0 (ワイド) → 中心 (クローズ) へ → ズームイン
            vf = (
                f"scale={sw}:{sh},"
                f"crop=w='{cw}':h='{ch}':"
                f"x='trunc({cx}*min(t,{D})/{D})':"
                f"y='trunc({cy}*min(t,{D})/{D})',"
                f"scale={w}:{h}"
            )
        elif motion == "zoom_out":
            # 中心 (クローズ) → 0,0 (ワイド) へ → ズームアウト
            vf = (
                f"scale={sw}:{sh},"
                f"crop=w='{cw}':h='{ch}':"
                f"x='trunc({cx}*(1-min(t,{D})/{D}))':"
                f"y='trunc({cy}*(1-min(t,{D})/{D}))',"
                f"scale={w}:{h}"
            )
        elif motion == "pan_left":
            # 右端→左端パン
            vf = (
                f"scale={sw}:{sh},"
                f"crop=w='{cw}':h='{ch}':"
                f"x='trunc(iw*(1-1/{scale})*(1-min(t,{D})/{D}))':"
                f"y='trunc({cy})',"
                f"scale={w}:{h}"
            )
        elif motion == "pan_right":
            # 左端→右端パン
            vf = (
                f"scale={sw}:{sh},"
                f"crop=w='{cw}':h='{ch}':"
                f"x='trunc(iw*(1-1/{scale})*min(t,{D})/{D})':"
                f"y='trunc({cy})',"
                f"scale={w}:{h}"
            )
        elif motion == "tilt_up":
            # 下→上ティルト
            vf = (
                f"scale={sw}:{sh},"
                f"crop=w='{cw}':h='{ch}':"
                f"x='trunc({cx})':"
                f"y='trunc(ih*(1-1/{scale})*(1-min(t,{D})/{D}))',"
                f"scale={w}:{h}"
            )
        elif motion == "tilt_down":
            # 上→下ティルト
            vf = (
                f"scale={sw}:{sh},"
                f"crop=w='{cw}':h='{ch}':"
                f"x='trunc({cx})':"
                f"y='trunc(ih*(1-1/{scale})*min(t,{D})/{D})',"
                f"scale={w}:{h}"
            )
        else:
            return

        tmp = clip_path.with_suffix(".motion_tmp.mp4")
        try:
            _sp.run([
                "ffmpeg", "-y", "-i", str(clip_path),
                "-vf", vf,
                "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-c:a", "copy",
                str(tmp),
            ], check=True, capture_output=True)
            tmp.replace(clip_path)
            logger.info("カメラモーション適用完了: %s", motion)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            logger.warning("カメラモーション適用失敗（スキップ）: %s", e)

    def _compose_avatar_with_background(
        self,
        avatar_path: Path,
        cinematic_prompt: str,
        output_path: Path,
    ) -> Path:
        """アバターを生成背景に合成する

        1. Flux で背景画像生成
        2. rembg でアバター写真から背景を除去
        3. PIL で人物を背景に込む
        失敗時は元の avatar_path を返す。
        """
        from PIL import Image
        import io as _io

        try:
            from rembg import remove as _rembg_remove
        except ImportError:
            logger.warning("rembg 未インストール → 背景合成スキップ")
            return avatar_path

        # 1. アバター画像サイズ取得
        try:
            avatar_img = Image.open(avatar_path)
            w, h = avatar_img.size
        except Exception as e:
            logger.warning("アバター画像ロード失敗: %s", e)
            return avatar_path

        # 2. Flux で背景生成
        bg_prompt = (
            f"background only, no people, no person, empty scene, "
            f"{cinematic_prompt}, high quality, realistic, 8K"
        )
        bg_path = output_path.parent / f"bg_{output_path.stem}.png"
        bg_generated = False
        try:
            flux = self._manager.get("flux")
            flux.generate(
                prompt=bg_prompt,
                output_path=bg_path,
                width=w,
                height=h,
                num_inference_steps=20,  # 背景は短ステップでOK
            )
            self._manager.unload_all()  # SadTalker の VRAM 主に解放
            bg_generated = bg_path.exists()
            logger.info("Flux 背景写真生成完了: %s", bg_path.name)
        except Exception as e:
            logger.warning("Flux 背景生成失敗 → 元アバター使用: %s", e)
            return avatar_path

        if not bg_generated:
            return avatar_path

        # 3. rembg でアバター背景除去
        try:
            with open(avatar_path, "rb") as f:
                avatar_bytes = f.read()
            fg_bytes = _rembg_remove(avatar_bytes)
            fg_img = Image.open(_io.BytesIO(fg_bytes)).convert("RGBA")
        except Exception as e:
            logger.warning("rembg 背景除去失敗 → 元アバター使用: %s", e)
            return avatar_path

        # 4. PIL で合成
        try:
            bg_img = Image.open(bg_path).convert("RGBA").resize(fg_img.size, Image.LANCZOS)
            bg_img.alpha_composite(fg_img)
            result = bg_img.convert("RGB")
            result.save(str(output_path))
            logger.info("背景合成完了: %s", output_path.name)
            return output_path
        except Exception as e:
            logger.warning("PIL 合成失敗 → 元アバター使用: %s", e)
            return avatar_path

    async def _generate_liveportrait_clip(
        self,
        image_path:     str,
        audio_path:     Path,
        clip_path:      Path,
        scene_index:    int,
        scene:          "ScriptScene | None" = None,
        on_progress:    "Callable[[int, str], Awaitable[None]] | None" = None,
        progress_start: int = 20,
        progress_end:   int = 85,
    ) -> Path:
        """LivePortrait + Wav2Lip でクリップを生成する

        1. LivePortrait: avatar.png + driving video → 体・頭・目の動き付き動画
        2. 音声長に合わせてループ/トリム
        3. Wav2Lip: 動体動画 + 音声 → リップシンク済み動画
        """
        import subprocess as _sp
        import asyncio as _asyncio
        import math as _math

        async def _progress(pct: int, msg: str) -> None:
            if on_progress:
                p = progress_start + int((progress_end - progress_start) * pct / 100)
                await on_progress(p, msg)

        await _progress(5, "LivePortrait: 体・頭の動きを生成中...")
        logger.info("LivePortrait 開始 (image=%s)", Path(image_path).name)

        lp_tmp_dir = clip_path.parent / f"_lp_tmp_{clip_path.stem}"
        lp_tmp_dir.mkdir(parents=True, exist_ok=True)
        loop = _asyncio.get_event_loop()

        # --- Step 1: LivePortrait アニメーション生成 ---
        def _run_liveportrait() -> "Path | None":
            cmd = [
                LIVEPORTRAIT_PYTHON,
                LIVEPORTRAIT_SCRIPT,
                "--source",  str(image_path),
                "--driving", LIVEPORTRAIT_DRIVING_DEFAULT,
                "--output-dir", str(lp_tmp_dir),
                "--flag-relative-motion",
                "--flag-stitching",
                "--no-flag-source-video-eye-retargeting",
                "--driving-smooth-observation-variance", "0.3",
            ]
            res = _sp.run(cmd, capture_output=True, text=True,
                          cwd=LIVEPORTRAIT_DIR, timeout=300)
            if res.returncode != 0:
                logger.error("LivePortrait 失敗:\n%s", res.stderr[-1000:])
                return None
            # 出力: {source_stem}--{driving_stem}.mp4
            src_stem = Path(image_path).stem
            drv_stem = Path(LIVEPORTRAIT_DRIVING_DEFAULT).stem
            expected = lp_tmp_dir / f"{src_stem}--{drv_stem}.mp4"
            if expected.exists():
                return expected
            # fallback: 最新 .mp4（_concat 除く）
            cands = sorted(
                [p for p in lp_tmp_dir.glob("*.mp4") if "_concat" not in p.name],
                key=lambda p: p.stat().st_mtime,
            )
            return cands[-1] if cands else None

        lp_out = await loop.run_in_executor(None, _run_liveportrait)

        if lp_out is None:
            logger.warning("LivePortrait 失敗 → SadTalker にフォールバック")
            import shutil as _sh2
            _sh2.rmtree(lp_tmp_dir, ignore_errors=True)
            return await self._generate_sadtalker_clip(
                image_path, audio_path, clip_path, scene_index, scene,
                on_progress, progress_start, progress_end,
            )

        await _progress(50, "LivePortrait: 音声長に合わせてトリム中...")

        # --- Step 2: 音声長に合わせてループ/トリム ---
        # 音声の長さを取得
        probe_audio = _sp.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True,
        )
        try:
            audio_dur = float(probe_audio.stdout.strip())
        except ValueError:
            audio_dur = 10.0

        # LivePortrait 出力の長さを取得
        probe_lp = _sp.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(lp_out)],
            capture_output=True, text=True,
        )
        try:
            lp_dur = float(probe_lp.stdout.strip())
        except ValueError:
            lp_dur = 5.0

        lp_looped = lp_tmp_dir / "lp_looped.mp4"
        loops = _math.ceil(audio_dur / lp_dur)
        if loops > 1:
            # concat でループ
            concat_txt = lp_tmp_dir / "loop.txt"
            concat_txt.write_text("\n".join([f"file '{lp_out}'" for _ in range(loops)]))
            _sp.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_txt),
                "-t", str(audio_dur),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-an",
                str(lp_looped),
            ], check=True, capture_output=True)
        else:
            # トリムのみ
            _sp.run([
                "ffmpeg", "-y", "-i", str(lp_out),
                "-t", str(audio_dur),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-an",
                str(lp_looped),
            ], check=True, capture_output=True)

        await _progress(65, "Wav2Lip: リップシンク追加中...")

        # --- Step 3: Wav2Lip でリップシンク ---
        WAV2LIP_FULLBODY = "/home/cocoro-influencer/scripts/wav2lip_fullbody.py"
        wav2lip_out = lp_tmp_dir / "wav2lip_out.mp4"
        res_w2l = _sp.run([
            WAV2LIP_PYTHON,
            WAV2LIP_FULLBODY,
            "--face",    str(lp_looped),
            "--audio",   str(audio_path),
            "--outfile", str(wav2lip_out),
        ], capture_output=True, text=True, timeout=900)

        if res_w2l.returncode != 0 or not wav2lip_out.exists():
            logger.warning("Wav2Lip 失敗 → 音声のみマージ\nSTDERR: %s",
                           res_w2l.stderr[-500:])
            # Wav2Lip 失敗時は音声だけマージして返す
            _sp.run([
                "ffmpeg", "-y",
                "-i", str(lp_looped), "-i", str(audio_path),
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                str(clip_path),
            ], check=True, capture_output=True)
        else:
            import shutil as _sh3
            _sh3.copy2(str(wav2lip_out), str(clip_path))
            logger.info("LivePortrait + Wav2Lip 完了 → %s", clip_path.name)

        # 後処理: カメラモーション
        if clip_path.exists() and scene is not None:
            motion = self._detect_camera_motion(scene)
            if motion != "static":
                probe = _sp.run(
                    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(clip_path)],
                    capture_output=True, text=True,
                )
                try:
                    duration = float(probe.stdout.strip())
                except ValueError:
                    duration = audio_dur
                await loop.run_in_executor(
                    None, self._apply_camera_motion, clip_path, motion, duration, 512, 512,
                )

        # 一時ディレクトリ削除
        import shutil as _sh4
        _sh4.rmtree(lp_tmp_dir, ignore_errors=True)

        return clip_path

    async def _generate_sadtalker_clip(
        self,
        image_path:     str,
        audio_path:     Path,
        clip_path:      Path,
        scene_index:    int,
        scene:          "ScriptScene | None" = None,
        on_progress:    "Callable[[int, str], Awaitable[None]] | None" = None,
        progress_start: int = 20,
        progress_end:   int = 85,
    ) -> Path:
        """SadTalker で talking_head クリップを生成する

        画像 + 音声 → SadTalker → リップシンク済み動画
        Wav2Lip/Wan2.1 より日本語に対応した高精度リップシンクを実現。
        """
        import subprocess as _sp
        import asyncio as _asyncio

        async def _progress(pct: int, msg: str) -> None:
            if on_progress:
                p = progress_start + int((progress_end - progress_start) * pct / 100)
                await on_progress(p, msg)

        await _progress(5, "SadTalker: リップシンク動画を生成中...")
        logger.info("Orchestrator: SadTalker 開始 (image=%s)", Path(image_path).name)

        loop = _asyncio.get_event_loop()

        def _run_sadtalker() -> bool:
            cmd = [
                SADTALKER_PYTHON,
                SADTALKER_SCRIPT,
                "--image",    str(image_path),
                "--audio",    str(audio_path),
                "--outfile",  str(clip_path),
                "--width",    "512",
                "--height",   "512",
                "--size",     "512",
                "--enhancer", "gfpgan",
                "--still",                         # 常に固定（--no-still は目の歪みが発生）
                "--expression_scale", "0.7",        # 口の動きを適度に抑制
                "--crf",      "18",
            ]
            result = _sp.run(cmd, capture_output=True, text=True, timeout=900)

            if result.returncode != 0 or not clip_path.exists():
                logger.warning(
                    "SadTalker失敗 (code=%d)\nSTDOUT:\n%s\nSTDERR:\n%s",
                    result.returncode,
                    result.stdout[-1000:],
                    result.stderr[-1000:],
                )
                return False
            logger.info("Orchestrator: SadTalker 完了 → %s", clip_path.name)
            return True

        ok = await loop.run_in_executor(None, _run_sadtalker)

        if not ok:
            logger.warning("Orchestrator: SadTalker 失敗 → Wav2Lip フォールバック")
            await _progress(50, "SadTalker失敗 → Wav2Lip フォールバック中...")
            fallback_video = clip_path.with_suffix(".fallback.mp4")
            _sp.run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
                "-c:v", "libx264", "-t", str(60),
                "-pix_fmt", "yuv420p", "-vf", "scale=512:512",
                "-r", "25", str(fallback_video),
            ], capture_output=True)
            if fallback_video.exists():
                w2l = _sp.run([
                    WAV2LIP_PYTHON, "/home/cocoro-influencer/scripts/wav2lip_fullbody.py",
                    "--face", str(fallback_video),
                    "--audio", str(audio_path),
                    "--outfile", str(clip_path),
                    "--crf", "18",
                ], capture_output=True, text=True, cwd=WAV2LIP_DIR, timeout=600)
                fallback_video.unlink(missing_ok=True)
                if w2l.returncode != 0:
                    logger.error("フォールバックWav2Lipも失敗")

        # ── カメラモーション適用 ───────────────────────────────────
        if clip_path.exists() and scene is not None:
            motion = self._detect_camera_motion(scene)
            logger.info("カメラモーション: %s (pose=%s, prompt=%s)",
                        motion, scene.pose, (scene.cinematic_prompt or "")[:40])
            if motion != "static":
                await _progress(95, f"カメラエフェクト適用中 ({motion})...")
                # 音声長を取得
                probe = _sp.run(
                    ["ffprobe", "-v", "quiet", "-show_entries",
                     "format=duration", "-of", "csv=p=0", str(clip_path)],
                    capture_output=True, text=True
                )
                try:
                    duration = float(probe.stdout.strip())
                except ValueError:
                    duration = 10.0
                loop2 = _asyncio.get_event_loop()
                await loop2.run_in_executor(
                    None,
                    self._apply_camera_motion,
                    clip_path, motion, duration, 512, 512,
                )

        await _progress(100, "SadTalker: 完了")
        return clip_path

    async def _generate_hunyuan_i2v_clip(
        self,
        image_path: str,
        audio_path: Path,
        clip_path: Path,
        scene_index: int,
        scene: "ScriptScene | None" = None,
        on_progress: "Callable[[int, str], Awaitable[None]] | None" = None,
        progress_start: int = 20,
        progress_end: int = 85,
    ) -> Path:
        """HunyuanVideo-I2V パイプライン

        1. HunyuanVideo-I2V で自然な動きの動画を生成
        2. 生成動画に音声をマージ（リップシンクなし）
        """
        import asyncio as _asyncio
        import subprocess as _sp
        import tempfile as _tempfile

        async def _progress(pct: int, msg: str) -> None:
            if on_progress:
                p = progress_start + int((progress_end - progress_start) * pct / 100)
                await on_progress(p, msg)

        await _progress(5, "HunyuanVideo-I2V: 高品質動画生成中（約3分）...")
        logger.info("HunyuanVideo-I2V 開始 (image=%s)", Path(image_path).name)

        # 音声長を取得してフレーム数計算
        probe = _sp.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True,
        )
        try:
            duration = float(probe.stdout.strip())
        except ValueError:
            duration = 5.0

        fps = 15
        raw = int(duration * fps) + 1
        # 4n+1 フレーム数（最大 201）
        k = max(4, (raw - 1) // 4)
        frame_num = min(4 * k + 1, 201)

        # 縦長ポートレート (480x832) を基本とする
        width  = getattr(self._config, "hunyuan_width",  480)
        height = getattr(self._config, "hunyuan_height", 832)
        steps  = getattr(self._config, "hunyuan_steps",  30)
        guidance = getattr(self._config, "hunyuan_guidance", 6.0)

        with _tempfile.TemporaryDirectory(prefix="hunyuan_i2v_") as tmpdir:
            tmp_video = str(Path(tmpdir) / "hunyuan_raw.mp4")
            tmp_with_audio = str(Path(tmpdir) / "hunyuan_audio.mp4")

            # --- Step 1: HunyuanVideo-I2V 推論 ---
            loop = _asyncio.get_event_loop()

            def _run_hunyuan() -> bool:
                cmd = [
                    HUNYUAN_I2V_PYTHON, HUNYUAN_I2V_SCRIPT,
                    "--image",          str(image_path),
                    "--prompt",         (
                        "professional presenter speaking naturally, "
                        "subtle head and body movement, talking to camera, "
                        "upper body visible, photorealistic"
                    ),
                    "--output",         tmp_video,
                    "--model_dir",      HUNYUAN_I2V_MODEL,
                    "--height",         str(height),
                    "--width",          str(width),
                    "--num_frames",     str(frame_num),
                    "--steps",          str(steps),
                    "--fps",            str(fps),
                    "--guidance_scale", str(guidance),
                ]
                res = _sp.run(cmd, capture_output=True, text=True, timeout=1200)
                if res.returncode != 0:
                    logger.error("HunyuanVideo-I2V エラー: %s", res.stderr[-2000:])
                    return False
                logger.info("HunyuanVideo-I2V 完了: %s", tmp_video)
                return True

            await _progress(10, "HunyuanVideo-I2V: 推論実行中...")
            ok = await loop.run_in_executor(None, _run_hunyuan)
            if not ok or not Path(tmp_video).exists():
                raise RuntimeError("HunyuanVideo-I2V 動画生成失敗")

            # --- Step 2: 音声マージ ---
            await _progress(85, "HunyuanVideo-I2V: 音声マージ中...")
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", tmp_video,
                "-i", str(audio_path),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                tmp_with_audio,
            ]
            _sp.run(trim_cmd, capture_output=True, check=False)

            src = tmp_with_audio if Path(tmp_with_audio).exists() else tmp_video
            import shutil
            shutil.copy2(src, str(clip_path))

        await _progress(100, "HunyuanVideo-I2V: 完了")
        logger.info("HunyuanVideo-I2V クリップ完了: %s", clip_path)
        return clip_path

    async def _generate_wan22_clip(
        self,
        image_path: str,
        audio_path: Path,
        clip_path: Path,
        scene_index: int,
        scene: "ScriptScene | None" = None,
        on_progress: "Callable[[int, str], Awaitable[None]] | None" = None,
        progress_start: int = 20,
        progress_end: int = 85,
    ) -> Path:
        """Wan2.2 I2V + Wav2Lip パイプライン

        1. Wan2.2 I2V で体・腕の動きを含む動画を生成
        2. Wav2Lip でリップシンクを追加
        """
        import asyncio as _asyncio
        import subprocess as _sp
        import tempfile as _tempfile

        async def _progress(pct: int, msg: str) -> None:
            if on_progress:
                p = progress_start + int((progress_end - progress_start) * pct / 100)
                await on_progress(p, msg)

        await _progress(5, "Wan2.2: 体・腕の動き生成中（約10分）...")
        logger.info("Wan2.2 I2V 開始 (image=%s)", Path(image_path).name)

        # 音声長を取得
        probe = _sp.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True,
        )
        try:
            duration = float(probe.stdout.strip())
        except ValueError:
            duration = 5.0

        # 4k+1 フレーム数計算 (最大 129)
        fps = 16
        raw = int(duration * fps) + 1
        k = max(8, (raw - 1) // 4)
        frame_num = min(4 * k + 1, 129)

        guide_scale = getattr(self._config, "wan22_guide_scale", 7.5)

        with _tempfile.TemporaryDirectory(prefix="wan22_") as tmpdir:
            tmp_wan  = str(Path(tmpdir) / "wan22_raw.mp4")
            tmp_trim = str(Path(tmpdir) / "wan22_trim.mp4")

            # --- Step 1: Wan2.2 I2V ---
            loop = _asyncio.get_event_loop()

            def _run_wan22() -> bool:
                cmd = [
                    WAN22_PYTHON, WAN22_SCRIPT,
                    "--task",               "i2v-A14B",
                    "--ckpt_dir",           WAN22_CKPT,
                    "--image",              str(image_path),
                    "--prompt",             (
                        "person speaking naturally, subtle arm gestures, "
                        "professional presenter, talking to camera, upper body visible"
                    ),
                    "--frame_num",          str(frame_num),
                    "--size",               "832*480",
                    "--save_file",          tmp_wan,
                    "--offload_model",      "true",
                    "--sample_guide_scale", str(guide_scale),
                ]
                res = _sp.run(cmd, capture_output=True, text=True,
                              cwd="/data/models/Wan2.2-repo", timeout=1200)
                if res.returncode != 0:
                    logger.error("Wan2.2 失敗:\n%s", res.stderr[-2000:])
                    return False
                return Path(tmp_wan).exists()

            ok = await loop.run_in_executor(None, _run_wan22)
            if not ok:
                logger.warning("Wan2.2 失敗 → LivePortrait フォールバック")
                return await self._generate_liveportrait_clip(
                    image_path, audio_path, clip_path, scene_index, scene,
                    on_progress, progress_start, progress_end,
                )

            await _progress(70, "Wan2.2: 音声長にトリム中...")

            # --- Step 2: 音声長にトリム ---
            _sp.run([
                "ffmpeg", "-y", "-i", tmp_wan,
                "-t", str(duration),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                tmp_trim,
            ], capture_output=True)

            await _progress(80, "Wan2.2: トリム完了（リップシンクはスキップ）")

            # --- Step 3: Wav2Lip リップシンク（Wan2.2 モードでは無効）---
            # Wav2Lip は英語向けに訓練されており、日本語では口元崩れが発生するため
            # Wan2.2 自体が生成する自然な口の動きをそのまま使用する。
            # 将来的に日本語対応リップシンク（MuseTalk 等）への差し替えポイント。
            import shutil as _sh
            _sh.copy2(tmp_trim, str(clip_path))
            logger.info("Wan2.2: Wav2Lip スキップ → Wan2.2 の自然な口の動きを使用")

        await _progress(100, "Wan2.2: 完了")
        logger.info("Wan2.2 クリップ生成完了: %s", clip_path.name)
        return clip_path

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
        """talking_head シーンを生成する（SadTalker 優先、フォールバック Wan2.1+Wav2Lip）

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

        # 既存クリップは削除して必ず再生成（ポーズ・設定変更を反映するため）
        if clip_path.exists():
            logger.info("Orchestrator: 既存クリップを削除して再生成 %s", clip_path)
            clip_path.unlink()

        # 入力画像選択
        image_path = self._select_pose_image(scene, avatar_path)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Wan2.2 分岐: 腕・体の動き最高品質（最優先）
        # use_wan22=True の場合はこちらを使用（LivePortrait/SadTalker より優先）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        use_w22 = getattr(self._config, "use_wan22", False)
        use_hunyuan = getattr(self._config, "use_hunyuan_i2v", False)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # HunyuanVideo-I2V 分岐: 高品質I2V（口元崩れ少・自然な動き）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if HUNYUAN_I2V_AVAILABLE and use_hunyuan:
            logger.info("HunyuanVideo-I2V パイプラインを使用 (avatar=%s)", avatar_path.name)
            return await self._generate_hunyuan_i2v_clip(
                image_path    = str(avatar_path.resolve()),
                audio_path    = audio_path,
                clip_path     = clip_path,
                scene_index   = scene_index,
                scene         = scene,
                on_progress   = on_progress,
                progress_start= progress_start,
                progress_end  = progress_end,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Wan2.2 分岐: 腕・体の動き最高品質（最優先）
        # use_wan22=True の場合はこちらを使用（LivePortrait/SadTalker より優先）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if WAN22_AVAILABLE and use_w22:
            logger.info("Wan2.2 I2V パイプラインを使用 (avatar=%s)", avatar_path.name)
            return await self._generate_wan22_clip(
                image_path    = str(avatar_path.resolve()),
                audio_path    = audio_path,
                clip_path     = clip_path,
                scene_index   = scene_index,
                scene         = scene,
                on_progress   = on_progress,
                progress_start= progress_start,
                progress_end  = progress_end,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # LivePortrait 分岐: 体・頭・目の動き + Wav2Lip リップシンク
        # SadTalker より優先（use_liveportrait=True の場合）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        use_lp = getattr(self._config, "use_liveportrait", False)
        if LIVEPORTRAIT_AVAILABLE and use_lp:
            logger.info("LivePortrait パイプラインを使用 (avatar=%s)", avatar_path.name)
            return await self._generate_liveportrait_clip(
                image_path    = str(avatar_path.resolve()),
                audio_path    = audio_path,
                clip_path     = clip_path,
                scene_index   = scene_index,
                scene         = scene,
                on_progress   = on_progress,
                progress_start= progress_start,
                progress_end  = progress_end,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SadTalker 分岐: 言語非依存の高精度リップシンク
        # SADTALKER_AVAILABLE かつ use_sadtalker=True の場合はこちらを使用
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if SADTALKER_AVAILABLE and self._config.use_sadtalker:
            sadtalker_image = str(avatar_path.resolve())
            logger.info("SadTalker: アバター画像使用 → %s", avatar_path.name)
            return await self._generate_sadtalker_clip(
                image_path    = sadtalker_image,
                audio_path    = audio_path,
                clip_path     = clip_path,
                scene_index   = scene_index,
                scene         = scene,
                on_progress   = on_progress,
                progress_start= progress_start,
                progress_end  = progress_end,
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 従来方式: Wan2.1 + Wav2Lip
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

        # talking_head / full_body 用プロンプト（カメラ構図で動きを使い分け）
        pose_desc = _POSE_PROMPT_MAP.get(scene.pose, "natural pose")
        if scene.camera_angle == "full_body":
            # 全身ショット: ポーズ別に矛盾のない動きプロンプトを使用
            motion_desc = _FULL_BODY_MOTION_MAP.get(scene.pose, "natural standing, subtle body sway")
            wan_prompt = (
                f"full body shot, {motion_desc}, "
                "consistent facial features, same person, high quality, photorealistic"
            )
        else:
            # 上半身: 顔・頭・肩の自然な動き
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
        # 古い中間ファイルも削除して再生成
        if wan_raw_path.exists():
            wan_raw_path.unlink()
        wan_ok = False

        # ⚡ Wan2.1実行前にOllamaモデルをVRAMからアンロード
        # Qwen2.5:32Bが27GiB占有したままだとWan2.1がOOMになるため
        _unload_ollama_models()

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

        # Wav2Lip リップシンク（v4.0: クロップ/オーバーレイなし直接方式）
        lipsync_path = clip_path.with_name(clip_path.stem + "_lipsync.mp4")
        try:
            logger.info("Orchestrator: Wav2Lip開始 (v4.0 直接方式, CRF=18)...")
            w2l_result = _sp.run([
                WAV2LIP_PYTHON,
                "/home/cocoro-influencer/scripts/wav2lip_fullbody.py",
                "--face",             str(wan_raw_path),
                "--audio",            str(audio_path),
                "--outfile",          str(lipsync_path),
                "--processing_width", "480",  # v4: 直接方式・動画全体処理
                "--crf",              "18",
            ], capture_output=True, text=True, cwd=WAV2LIP_DIR,
               timeout=600)

            if w2l_result.returncode == 0 and lipsync_path.exists():
                _sh.copy(str(lipsync_path), str(clip_path))
                logger.info("Orchestrator: Wav2Lip完了 → %s", clip_path)
            else:
                # ⚠️ 詳細なエラー情報をログに出力（デバッグ用）
                logger.warning(
                    "Orchestrator: Wav2Lip失敗(code=%d) → Wan2.1動画を使用\n"
                    "=== STDOUT ===\n%s\n=== STDERR ===\n%s",
                    w2l_result.returncode,
                    w2l_result.stdout[-1000:],
                    w2l_result.stderr[-2000:],
                )
                _sh.copy(str(wan_raw_path), str(clip_path))
        except _sp.TimeoutExpired:
            logger.warning("Orchestrator: Wav2Lipタイムアウト(600s) → Wan2.1動画を使用")
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
            logger.info("Orchestrator: Kling全身Wav2Lip開始 (scale=720, CRF=18)...")
            w2l_result = _sp.run([
                WAV2LIP_PYTHON,
                "/home/cocoro-influencer/scripts/wav2lip_fullbody.py",
                "--face",          str(kling_video_path),
                "--audio",         str(audio_path),
                "--outfile",       str(lipsync_path),
                "--lipsync_scale", "720",
                "--padding_ratio", "0.4",   # 全身は顔小さいため大きめ
                "--crf",           "18",
            ], capture_output=True, text=True, cwd=WAV2LIP_DIR,
               timeout=600)

            if w2l_result.returncode == 0 and lipsync_path.exists():
                _sh.copy(str(lipsync_path), str(clip_path))
                logger.info("Orchestrator: 全身Wav2Lip完了 %s", clip_path)
            else:
                logger.warning(
                    "Orchestrator: 全身Wav2Lip失敗(code=%d) → Kling動画を使用\nSTDOUT: %s\nSTDERR: %s",
                    w2l_result.returncode,
                    w2l_result.stdout[-300:],
                    w2l_result.stderr[-500:],
                )
                _sh.copy(str(kling_video_path), str(clip_path))
        except _sp.TimeoutExpired:
            logger.warning("Orchestrator: Kling Wav2Lipタイムアウト → Kling動画を使用")
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

        pose_desc = _POSE_PROMPT_MAP.get(scene.pose, "natural pose")
        if scene.camera_angle == "full_body":
            # 全身ショット: ポーズ別の動きプロンプトを使用 (矛盾するワード混在を防ぐ)
            motion_desc = _FULL_BODY_MOTION_MAP.get(scene.pose, "natural standing, subtle body sway")
            base_prompt = scene.cinematic_prompt or "modern studio, professional lighting"
            prompt_parts = [
                "full body shot",
                motion_desc,
                "consistent facial features, same person, photorealistic face",
                base_prompt,
                "high quality, cinematic, photorealistic",
            ]
        else:
            base_prompt = scene.cinematic_prompt or "professional video, smooth camera movement"
            prompt_parts = [
                base_prompt,
                "high quality, cinematic, photorealistic",
            ]
        if scene.appearance_prompt:
            prompt_parts.insert(0, scene.appearance_prompt)
        full_prompt = ", ".join(p for p in prompt_parts if p)


        logger.info(
            "Orchestrator: Wan2.1 シネマティック生成 (frames=%d, %.1f秒): %s",
            target_frames, audio_duration, full_prompt[:60],
        )

        # ⚡ Wan2.1実行前にOllamaモデルをVRAMからアンロード
        _unload_ollama_models()

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
        # ※ テキスト変更を確実に反映するため既存ファイルを削除して必ず再生成
        audio_path = config.output_dir / f"scene_{scene_index:03d}_voice.wav"
        if audio_path.exists():
            audio_path.unlink()
            logger.info("Orchestrator: 既存音声ファイルを削除して再生成 %s", audio_path)
        await _progress(10, "音声合成中 (Style-Bert-VITS2)...")
        voice_engine = self._manager.get("voice")
        voice_engine.generate(text=scene.text, output_path=audio_path, speed_scale=config.speech_speed)
        await _progress(30, "音声合成完了 → Wan2.1動画生成開始...")

        # 音声長取得
        with wave.open(str(audio_path), "rb") as wf:
            audio_duration = wf.getnframes() / wf.getframerate()

        # Step 2: 動画生成（Wan2.1 + Wav2Lip）
        # full_body または cinematic は _generate_cinematic_clip を使う
        # (動き幅が広い全身シーンは cinematic 設定のほうが適している)
        use_cinematic = (
            scene.scene_type == "cinematic"
            or scene.camera_angle == "full_body"
        )
        if use_cinematic:
            clip_path = await self._generate_cinematic_clip(
                scene=scene,
                scene_index=scene_index,
                audio_path=audio_path,
                audio_duration=audio_duration,
                avatar_path=avatar_path,
                on_progress=on_progress,
                progress_start=35,
                progress_end=95,
            )
        else:
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
            # ※ テキスト変更を確実に反映するため既存ファイルを削除して必ず再生成
            audio_path = config.output_dir / f"scene_{i:03d}_voice.wav"
            if audio_path.exists():
                audio_path.unlink()
                logger.info("Orchestrator: 既存音声ファイルを削除して再生成 %s", audio_path)
            await _progress(scene_base + 2, f"音声合成中... ({i+1}/{total_scenes})")
            voice_engine = self._manager.get("voice")
            voice_engine.generate(
                text=scene.text,
                output_path=audio_path,
                model_id=config.model_id,
                speed_scale=config.speech_speed,
            )

            # 音声長を取得
            with wave.open(str(audio_path), "rb") as wf:
                audio_duration = wf.getnframes() / wf.getframerate()

            # Step 3: 動画生成 (on_progress を伝播して進捗をリアルタイム更新)
            # ※ 毎回必ず再生成（ポーズ・設定変更を確実に反映）
            await _progress(scene_base + 5, f"動画生成中 (Wan2.1)... ({i+1}/{total_scenes})")
            # full_body または cinematic は動き幅が大きいため cinematic クリップ生成を使用
            use_cinematic = (
                scene.scene_type == "cinematic"
                or scene.camera_angle == "full_body"
            )
            if use_cinematic:
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

            # テロップ登録: enable_subtitles=True の場合は scene.caption （台本テキスト）を自動設定
            caption_text = scene.caption
            if config.enable_subtitles and not caption_text:
                caption_text = scene.text
            if caption_text:
                captions.append(Caption(
                    text=caption_text,
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
            bgm_volume=config.bgm_volume,
            captions=captions,
            output_format=config.output_format,
            transition=config.transition,
            transition_duration=config.transition_duration,
            watermark_path=config.watermark_path,
            watermark_position=config.watermark_position,
            watermark_scale=config.watermark_scale,
        )
        self._compositor.compose(composite_config)

        logger.info("Orchestrator: パイプライン完了 → %s", final_path)
        self._manager.unload_all()
        return final_path
