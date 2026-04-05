<<<<<<< HEAD
"""cocoro-inf: 企業専属AIインフルエンサー生成CLI (Phase 4)

typerによるコマンドラインインターフェース。
Phase 1: avatar generate
Phase 2: voice generate / talking-head generate / cinematic generate / compose
Phase 4: script generate / pipeline run

使用例:
    cocoro-inf avatar generate --prompt "ビジネススーツの日本人女性" --output ./outputs/avatar.png
    cocoro-inf voice generate --text "こんにちは" --output ./outputs/voice.wav
    cocoro-inf talking-head generate --image avatar.png --audio voice.wav --output clip.mp4
    cocoro-inf cinematic generate --image avatar.png --prompt "オフィスで" --output scene.mp4
    cocoro-inf compose --clips clip.mp4 scene.mp4 --format youtube --output final.mp4
    cocoro-inf script generate --company "株式会社Example" --product "AIプラットフォーム"
    cocoro-inf pipeline run --company "Example" --product "サービス" --output-dir ./outputs/example
"""

import logging
from pathlib import Path

import typer

from src.engines.echomimic_engine import EchoMimicEngine
from src.engines.flux_engine import FluxEngine
from src.engines.manager import EngineManager
from src.engines.voice_engine import VoiceEngine
from src.engines.wan_engine import WanEngine
from src.pipeline.compositor import CompositeConfig, Compositor

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# メインアプリ
app = typer.Typer(
    name="cocoro-inf",
    help="企業専属AIインフルエンサー生成システム",
    no_args_is_help=True,
)

# --- サブコマンドグループ ---
avatar_app = typer.Typer(help="アバター画像生成", no_args_is_help=True)
voice_app = typer.Typer(help="音声合成 (VOICEVOX)", no_args_is_help=True)
talking_head_app = typer.Typer(help="リップシンクトーキングヘッド生成", no_args_is_help=True)
cinematic_app = typer.Typer(help="シネマティック動画生成 (Wan 2.6 I2V)", no_args_is_help=True)
script_app = typer.Typer(help="LLM台本自動生成 (Gemini/Claude)", no_args_is_help=True)
pipeline_app = typer.Typer(help="フルパイプライン実行 (台本→動画)", no_args_is_help=True)
agent_app = typer.Typer(help="cocoro-OSエージェント管理", no_args_is_help=True)

app.add_typer(avatar_app, name="avatar")
app.add_typer(voice_app, name="voice")
app.add_typer(talking_head_app, name="talking-head")
app.add_typer(cinematic_app, name="cinematic")
app.add_typer(script_app, name="script")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(agent_app, name="agent")


# ===========================================================
# avatar generate
# ===========================================================
@avatar_app.command("generate")
def avatar_generate(
    prompt: str = typer.Option(..., "--prompt", "-p", help="画像生成プロンプト"),
    output: Path = typer.Option(..., "--output", "-o", help="出力PNGパス"),
    lora: Path | None = typer.Option(None, "--lora", "-l", help="LoRAパス (オプション)"),
    width: int = typer.Option(1024, "--width", "-W", help="幅 (px)"),
    height: int = typer.Option(1024, "--height", "-H", help="高さ (px)"),
    steps: int = typer.Option(30, "--steps", "-s", help="推論ステップ数"),
    seed: int | None = typer.Option(None, "--seed", help="ランダムシード"),
) -> None:
    """FLUX.2 + LoRA でアバター画像を生成する"""
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        manager = EngineManager()
        manager.register("flux", FluxEngine())
        engine = manager.get("flux")
        result_path = engine.generate(
            prompt=prompt,
            output_path=output,
            lora_path=lora,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=7.5,
            seed=seed,
        )
        typer.echo(f"✅ アバター画像を生成しました: {result_path}")
    except (FileNotFoundError, RuntimeError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# voice generate
# ===========================================================
@voice_app.command("generate")
def voice_generate(
    text: str = typer.Option(..., "--text", "-t", help="読み上げテキスト"),
    output: Path = typer.Option(..., "--output", "-o", help="出力WAVパス"),
    speaker: int = typer.Option(3, "--speaker", help="話者ID (デフォルト: 3=ずんだもん)"),
    speed: float = typer.Option(1.0, "--speed", help="話速 (1.0=標準)"),
    voicevox_url: str = typer.Option("http://localhost:50021", "--voicevox-url", help="VOICEVOX ENGINE URL"),
) -> None:
    """VOICEVOX で日本語音声を合成する"""
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        manager = EngineManager()
        manager.register("voice", VoiceEngine(voicevox_url=voicevox_url))
        engine = manager.get("voice")
        result_path = engine.generate(
            text=text,
            output_path=output,
            speaker_id=speaker,
            speed_scale=speed,
        )
        typer.echo(f"✅ 音声を生成しました: {result_path}")
    except (FileNotFoundError, RuntimeError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# talking-head generate
# ===========================================================
@talking_head_app.command("generate")
def talking_head_generate(
    image: Path = typer.Option(..., "--image", help="入力アバター画像パス"),
    audio: Path = typer.Option(..., "--audio", help="入力音声WAVパス"),
    output: Path = typer.Option(..., "--output", "-o", help="出力MP4パス"),
    width: int = typer.Option(512, "--width", help="出力動画幅 (px)"),
    height: int = typer.Option(512, "--height", help="出力動画高さ (px)"),
    steps: int = typer.Option(20, "--steps", help="推論ステップ数"),
    seed: int | None = typer.Option(None, "--seed", help="ランダムシード"),
) -> None:
    """EchoMimic でリップシンクトーキングヘッド動画を生成する"""
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        manager = EngineManager()
        manager.register("echomimic", EchoMimicEngine())
        engine = manager.get("echomimic")
        result_path = engine.generate(
            image_path=image,
            audio_path=audio,
            output_path=output,
            width=width,
            height=height,
            num_inference_steps=steps,
            seed=seed,
        )
        typer.echo(f"✅ トーキングヘッド動画を生成しました: {result_path}")
    except (FileNotFoundError, RuntimeError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# cinematic generate
# ===========================================================
@cinematic_app.command("generate")
def cinematic_generate(
    image: Path = typer.Option(..., "--image", help="入力画像パス"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="動画生成プロンプト"),
    output: Path = typer.Option(..., "--output", "-o", help="出力MP4パス"),
    frames: int = typer.Option(81, "--frames", help="生成フレーム数"),
    steps: int = typer.Option(50, "--steps", help="推論ステップ数"),
    seed: int | None = typer.Option(None, "--seed", help="ランダムシード"),
) -> None:
    """Wan 2.6 I2V でシネマティック動画を生成する"""
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        manager = EngineManager()
        manager.register("wan", WanEngine())
        engine = manager.get("wan")
        result_path = engine.generate(
            image_path=image,
            prompt=prompt,
            output_path=output,
            num_frames=frames,
            num_inference_steps=steps,
            seed=seed,
        )
        typer.echo(f"✅ シネマティック動画を生成しました: {result_path}")
    except (FileNotFoundError, RuntimeError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# compose
# ===========================================================
@app.command("compose")
def compose(
    clips: list[Path] = typer.Option(..., "--clips", help="入力クリップパス (複数指定可)"),
    output: Path = typer.Option(..., "--output", "-o", help="出力MP4パス"),
    bgm: Path | None = typer.Option(None, "--bgm", help="BGMファイルパス (オプション)"),
    fmt: str = typer.Option("youtube", "--format", "-f", help="出力フォーマット (youtube/shorts/instagram)"),
    bgm_volume: float = typer.Option(0.15, "--bgm-volume", help="BGM音量 (0.0〜1.0)"),
) -> None:
    """FFmpeg で動画クリップを合成する (BGM追加・テロップ付き)"""
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        compositor = Compositor()
        config = CompositeConfig(
            clips=clips,
            output_path=output,
            bgm_path=bgm,
            output_format=fmt,
            bgm_volume=bgm_volume,
        )
        result_path = compositor.compose(config)
        typer.echo(f"✅ 動画を合成しました: {result_path}")
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# script generate (Phase 4)
# ===========================================================
@script_app.command("generate")
def script_generate(
    company: str = typer.Option(..., "--company", "-c", help="企業名"),
    product: str = typer.Option(..., "--product", "-p", help="製品/サービス名"),
    output: Path = typer.Option(Path("outputs/script.json"), "--output", "-o", help="出力JSONパス"),
    audience: str = typer.Option("20代〜40代のビジネスパーソン", "--audience", help="ターゲット視聴者"),
    tone: str = typer.Option("プロフェッショナルで親しみやすい", "--tone", help="動画のトーン"),
    duration: str = typer.Option("60秒", "--duration", help="動画の目標長さ"),
    provider: str = typer.Option("gemini", "--provider", help="LLMプロバイダー (gemini/anthropic)"),
    model: str | None = typer.Option(None, "--model", help="モデル名 (省略時はデフォルト)"),
) -> None:
    """LLM (Gemini/Claude) で企業向け動画台本を自動生成する

    環境変数 GEMINI_API_KEY または ANTHROPIC_API_KEY が必要。
    """
    try:
        from src.engines.script_engine import ScriptEngine

        engine = ScriptEngine(provider=provider, model=model)
        engine.load()
        output.parent.mkdir(parents=True, exist_ok=True)
        script = engine.generate(
            company_name=company,
            product_name=product,
            target_audience=audience,
            tone=tone,
            duration=duration,
            output_path=output,
        )
        typer.echo(f"✅ 台本を生成しました: {output}")
        typer.echo(f"   タイトル: {script.title}")
        typer.echo(f"   シーン数: {len(script.scenes)}")
        for i, scene in enumerate(script.scenes, 1):
            typer.echo(f"   [{i}] ({scene.scene_type}) {scene.text[:40]}...")
    except (RuntimeError, FileNotFoundError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# pipeline run (Phase 4)
# ===========================================================
@pipeline_app.command("run")
def pipeline_run(
    company: str = typer.Option(..., "--company", "-c", help="企業名"),
    product: str = typer.Option(..., "--product", "-p", help="製品/サービス名"),
    output_dir: Path = typer.Option(..., "--output-dir", "-o", help="出力ディレクトリ"),
    script_file: Path | None = typer.Option(None, "--script", "-s", help="既存台本JSONパス (省略時はLLM生成)"),
    lora: Path | None = typer.Option(None, "--lora", "-l", help="LoRAパス (オプション)"),
    bgm: Path | None = typer.Option(None, "--bgm", help="BGMパス (オプション)"),
    fmt: str = typer.Option("youtube", "--format", "-f", help="出力フォーマット"),
    provider: str = typer.Option("gemini", "--provider", help="LLMプロバイダー (台本生成時)"),
) -> None:
    """台本 → 音声 → 動画 → 合成のフルパイプラインを実行する

    --script を指定しない場合は LLM で台本を自動生成する。
    """
    try:
        from src.engines.script_engine import ScriptEngine
        from src.pipeline.orchestrator import Orchestrator, PipelineConfig
        from src.pipeline.orchestrator import ScriptScene as OrchestratorScene
        from src.pipeline.script_parser import script_to_pipeline_config

        # 台本の取得
        if script_file is not None:
            typer.echo(f"📄 台本ファイルを読み込みます: {script_file}")
            script = ScriptEngine.load_from_file(script_file)
        else:
            typer.echo(f"🤖 LLMで台本を生成します ({provider})...")
            engine = ScriptEngine(provider=provider)
            engine.load()
            script_output = output_dir / "script.json"
            script_output.parent.mkdir(parents=True, exist_ok=True)
            script = engine.generate(
                company_name=company,
                product_name=product,
                output_path=script_output,
            )
            typer.echo(f"✅ 台本生成完了: {script.title} ({len(script.scenes)}シーン)")

        # PipelineConfigに変換
        pipeline_config = script_to_pipeline_config(
            script,
            output_dir=output_dir,
            lora_path=lora,
            bgm_path=bgm,
            output_format=fmt,
        )

        typer.echo("🚀 パイプラインを実行します...")
        orchestrator = Orchestrator(pipeline_config)
        final_path = orchestrator.run()

        typer.echo(f"✅ フルパイプライン完了: {final_path}")

    except (RuntimeError, FileNotFoundError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# pipeline list-scenes (台本プレビュー)
# ===========================================================
@pipeline_app.command("preview")
def pipeline_preview(
    script_file: Path = typer.Option(..., "--script", "-s", help="台本JSONファイルパス"),
) -> None:
    """台本JSONの内容をプレビュー表示する"""
    try:
        from src.engines.script_engine import ScriptEngine

        script = ScriptEngine.load_from_file(script_file)
        typer.echo(f"\n📋 台本: {script.title}")
        typer.echo(f"   企業: {script.company_name} / 製品: {script.product_name}")
        typer.echo(f"   シーン数: {len(script.scenes)} | 予想長さ: {script.total_duration_estimate}")
        typer.echo(f"   アバタープロンプト: {script.avatar_prompt[:60]}...")
        typer.echo("\n📝 シーン一覧:")
        for scene in script.scenes:
            icon = "🗣️" if scene.scene_type == "talking_head" else "🎬"
            typer.echo(f"  {icon} [{scene.scene_id}] {scene.scene_type}")
            typer.echo(f"      テキスト: {scene.text[:60]}...")
            if scene.caption:
                typer.echo(f"      テロップ: {scene.caption}")
            if scene.cinematic_prompt:
                typer.echo(f"      Cinematic: {scene.cinematic_prompt[:60]}...")
    except (FileNotFoundError, RuntimeError) as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


# ===========================================================
# agent start (Phase 5)
# ===========================================================
@agent_app.command("start")
def agent_start(
    core_url: str = typer.Option(
        "http://192.168.50.92:8001", "--core-url", "-u", help="cocoro-OS CORE_URL"
    ),
    api_key: str = typer.Option(
        "cocoro-2026", "--api-key", "-k", help="cocoro-OS APIキー"
    ),
    poll_interval: float = typer.Option(
        5.0, "--poll-interval", help="タスクポーリング間隔 (秒)"
    ),
    heartbeat_interval: float = typer.Option(
        30.0, "--heartbeat-interval", help="ハートビート送信間隔 (秒)"
    ),
) -> None:
    """cocoro-OSエージェントとして起動してタスクを受信・実行する

    Ctrl+Cで正常終了する。
    """
    from src.agent.interface import CocoroAgentConfig
    from src.agent.worker import CocoroWorker

    typer.echo(f"🚀 cocoro-influencer エージェントを起動します")
    typer.echo(f"   CORE_URL   : {core_url}")
    typer.echo(f"   Poll       : {poll_interval}s")
    typer.echo(f"   Heartbeat  : {heartbeat_interval}s")
    typer.echo("   Ctrl+C で終了")

    config = CocoroAgentConfig(
        cocoro_core_url=core_url,
        cocoro_api_key=api_key,
    )
    worker = CocoroWorker(
        config=config,
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
    )
    try:
        worker.run()
    except Exception as e:
        typer.echo(f"❌ エラー: {e}", err=True)
        raise typer.Exit(code=1) from e


@agent_app.command("status")
def agent_status(
    core_url: str = typer.Option(
        "http://192.168.50.92:8001", "--core-url", "-u", help="cocoro-OS CORE_URL"
    ),
    api_key: str = typer.Option(
        "cocoro-2026", "--api-key", "-k", help="cocoro-OS APIキー"
    ),
) -> None:
    """cocoro-OSへの接続疎通確認を行う"""
    import httpx

    typer.echo(f"🔍 cocoro-OS 接続確認: {core_url}")
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{core_url.rstrip('/')}/health",
                headers={
                    "X-API-Key": api_key,
                    "X-Schema-Version": "v7",
                },
            )
        if response.status_code < 300:
            data = response.json() if response.content else {}
            typer.echo(f"✅ cocoro-OS 接続成功: {data}")
        else:
            typer.echo(f"⚠️ cocoro-OS レスポンス: {response.status_code}")
    except httpx.HTTPError as e:
        typer.echo(f"❌ 接続失敗: {e}", err=True)
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()
=======
"""
Avatar Video Pipeline - メインオーケストレーター

3Dアバターから実写風AI動画を全自動生成するパイプラインの制御。
処理フロー:
  1. Blender: VRMモデル → ポーズ付き3Dレンダリング（RGB + Depth + Canny）
  2. ComfyUI (FLUX + ControlNet): 3Dレンダリング → 実写風画像
  3. ComfyUI (Wan 2.1 I2V): 実写画像 → 動画クリップ
  4. TTS: 台本テキスト → 音声ファイル
  5. ComfyUI (LivePortrait): 動画 + 音声 → リップシンク動画
  6. Editor (MoviePy + FFmpeg): シーン結合 → 最終MP4
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import load_settings, PROJECT_ROOT

# ── ロギング設定 ──────────────────────────────────────────────
def setup_logging(level: str = "INFO"):
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8"),
        ],
    )

logger = logging.getLogger("pipeline")


# ── データモデル ──────────────────────────────────────────────
@dataclass
class SceneSpec:
    """1シーンの仕様"""
    scene_id: str
    script_text: str                      # セリフ・ナレーション
    pose: str = "neutral"                 # ポーズ名 (pose_library.json参照)
    expression: str = "neutral"           # 表情名
    duration: float = 5.0                 # 秒
    camera_angle: str = "upper_body"      # カメラアングル (full_body, upper_body, close_up)
    background: Optional[str] = None      # 背景画像パス（オプション）
    appearance_prompt: str = "photorealistic, highly detailed, 8k resolution, cinematic lighting, 1girl, upper body, beautiful face, business suit"
    background_prompt: str = "in a modern office, bright lighting"
    negative_prompt: str = "anime, text, watermark, worst quality"


@dataclass
class JobSpec:
    """動画生成ジョブ全体の仕様"""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    avatar_path: str = ""                  # VRMモデルパス
    scenes: List[SceneSpec] = field(default_factory=list)
    bgm_path: Optional[str] = None        # BGMファイルパス
    output_path: str = "output/final.mp4"
    resolution: tuple = (1280, 720)       # 出力解像度


@dataclass
class PipelineResult:
    """パイプライン実行結果"""
    success: bool
    job_id: str
    output_path: Optional[str] = None
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    scene_results: List[dict] = field(default_factory=list)


# ── パイプラインステージ ────────────────────────────────────
class Pipeline:
    """メインパイプライン"""

    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.work_dir = PROJECT_ROOT / "tmp" / f"job_{int(time.time())}"
        self._comfyui_runner = None
        self._tts_manager = None
        self._compositor = None

    def _get_comfyui_runner(self):
        # [ハイブリッド] ComfyUIモジュールは今後使用せず、APIモジュールに移行します。
        return None

    def _get_tts_manager(self):
        if self._tts_manager is None:
            from src.modules.voice_gen.local_tts.engine import TTSManager
            self._tts_manager = TTSManager(self.settings)
        return self._tts_manager

    def _get_compositor(self):
        if self._compositor is None:
            from src.modules.compositor.moviepy_editor.compositor import VideoCompositor
            self._compositor = VideoCompositor(
                ffmpeg_path=self.settings.ffmpeg.path,
                encoder=self.settings.ffmpeg.encoder,
                hwaccel=self.settings.ffmpeg.hwaccel,
                quality=self.settings.ffmpeg.quality,
            )
        return self._compositor

    async def run(self, job: JobSpec, approval_callback=None, progress_callback=None) -> PipelineResult:
        """パイプライン全体を実行"""
        start_time = time.time()
        self.work_dir = PROJECT_ROOT / "tmp" / f"job_{job.job_id}"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"╔════════════════════════════════════════════════╗")
        logger.info(f"║  パイプライン開始: Job {job.job_id}")
        logger.info(f"║  シーン数: {len(job.scenes)}")
        logger.info(f"║  アバター: {job.avatar_path}")
        logger.info(f"╚════════════════════════════════════════════════╝")

        result = PipelineResult(success=True, job_id=job.job_id)

        try:
            # ── ステージ1: 全シーンの3Dレンダリング ──
            logger.info("━━━ Stage 1/5: Blender 3Dレンダリング ━━━")
            if progress_callback: await progress_callback(10, "Stage 1: Blenderを用いて3Dポーズを出力中...")
            while True:
                render_outputs = await self._stage_blender(job)
                if approval_callback and not render_outputs[0].get("is_fallback", False):
                    action = await approval_callback("Stage1_Blender_3D", render_outputs[0]["rgb"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 1)")
                break

            # ── ステージ2: AI実写化 (FLUX + ControlNet) ──
            logger.info("━━━ Stage 2/5: AI実写化 (FLUX + ControlNet) ━━━")
            if progress_callback: await progress_callback(30, "Stage 2: FLUX + ControlNet で実写化中... (1分〜2分)")
            while True:
                realify_outputs = await self._stage_realify(job, render_outputs)
                if approval_callback:
                    action = await approval_callback("Stage2_FLUX_実写化", realify_outputs[0]["image"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 2)")
                break

            # ── ステージ3: TTS音声合成 ──
            logger.info("━━━ Stage 3/5: TTS音声合成 ━━━")
            if progress_callback: await progress_callback(50, "Stage 3: TTSエンジン (Style-Bert-VITS2) で音声合成中...")
            while True:
                audio_outputs = await self._stage_tts(job)
                if approval_callback:
                    action = await approval_callback("Stage3_音声合成", audio_outputs[0]["audio"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 3)")
                break

            # ── ステージ4: AI動画生成 + リップシンク ──
            logger.info("━━━ Stage 4/5: AI動画生成 (Wan 2.1) + リップシンク ━━━")
            if progress_callback: await progress_callback(70, "Stage 4: Wan 2.1 動画生成中... 今しばらくお待ちください (約15〜20分)")
            
            while True:
                # Combine realify and audio outputs for stage 4
                combined_results = []
                for i, (r_out, a_out) in enumerate(zip(realify_outputs, audio_outputs)):
                    combined_results.append({
                        "scene_id": r_out["scene_id"],
                        "image": r_out["image"],
                        "audio": a_out["audio"],
                        "duration": a_out["duration"],
                    })

                video_outputs = await self._stage_video(job, combined_results)
                if approval_callback and video_outputs and "video" in video_outputs[0]:
                    action = await approval_callback("Stage4_Wan_動画生成", video_outputs[0]["video"])
                    if action == "retry": continue
                    if action == "reject": raise Exception("キャンセルされました(Stage 4)")
                break

            # ── ステージ5: 自動編集・結合 ──
            logger.info("━━━ Stage 5/5: 自動編集・結合 ━━━")
            if progress_callback: await progress_callback(95, "Stage 5: LivePortrait (リップシンク) 適用・エンコード中...")
            final_path = await self._stage_compose(job, video_outputs)

            elapsed = time.time() - start_time
            logger.info(f"✅ パイプライン完了: {final_path} ({elapsed:.1f}秒)")

            result.output_path = str(final_path)
            result.scene_results = video_outputs
            result.elapsed_seconds = elapsed
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ パイプラインエラー: {e}", exc_info=True)
            return PipelineResult(
                success=False,
                job_id=job.job_id,
                elapsed_seconds=elapsed,
                error=str(e),
            )

    # ── 各ステージのプレースホルダー ──────────────────────────

    async def _stage_blender(self, job: JobSpec) -> List[dict]:
        """
        Blenderヘッドレスを使用してVRMアバターをレンダリング。
        各シーンに対して RGB, Depth, Canny 画像を出力。
        """
        import subprocess as sp

        blender_exe = self.settings.blender.path
        script_path = str(PROJECT_ROOT / "blender" / "render_avatar.py")
        outputs = []

        for i, scene in enumerate(job.scenes):
            scene_dir = self.work_dir / f"scene_{i:03d}" / "render"
            scene_dir.mkdir(parents=True, exist_ok=True)
            rgb_path = scene_dir / "rgb.png"
            depth_path = scene_dir / "depth.png"

            # もしアバター指定が画像（A: 画像アップロード機能）だった場合は、Blenderをスキップして画像をそのまま配置
            avatar_path_lower = str(job.avatar_path).lower()
            if avatar_path_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
                logger.info(f"  [{i+1}/{len(job.scenes)}] カスタムキャラクター画像がアップロードされています。Blenderをスキップします。")
                import shutil
                shutil.copy(str(PROJECT_ROOT / job.avatar_path), str(rgb_path))
            else:
                logger.info(f"  [{i+1}/{len(job.scenes)}] ポーズ={scene.pose}, 表情={scene.expression}")

                cmd = [
                    blender_exe, "-b",
                    "--python", script_path, "--",
                    "--vrm", str(PROJECT_ROOT / job.avatar_path),
                    "--pose", scene.pose,
                    "--expression", scene.expression,
                    "--camera", scene.camera_angle,
                    "--output", str(scene_dir),
                    "--width", str(self.settings.blender.render_width),
                    "--height", str(self.settings.blender.render_height),
                    "--engine", f"BLENDER_{self.settings.blender.render_engine}",
                ]

                try:
                    result = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await result.communicate()
                    if result.returncode != 0:
                        logger.warning(f"  ⚠ Blenderレンダリング警告 (scene {i}): {stderr.decode(errors='replace')[:200]}")
                except FileNotFoundError:
                    logger.warning(f"  ⚠ Blender未検出: {blender_exe} - スキップ")

            # Blenderが使えない場合のフォールバック（テストモード用）
            is_fallback = False
            if not rgb_path.exists():
                import shutil
                fallback_candidates = [
                    Path(r"F:\ComfyUI\input\realify_s_000.png"),
                    Path(r"F:\ComfyUI\input\e2e_test_result.png"),
                    Path(r"F:\ComfyUI\input\test_avatar_rgb.png"),
                ]
                for candidate in fallback_candidates:
                    if candidate.exists():
                        shutil.copy(str(candidate), str(rgb_path))
                        logger.warning(f"  Blender出力なし -> フォールバック使用: {candidate.name}")
                        is_fallback = True
                        break

            if not depth_path.exists() and rgb_path.exists():
                import shutil
                shutil.copy(str(rgb_path), str(depth_path))  # depthも同じ画像で代替

            outputs.append({
                "scene_id": scene.scene_id,
                "rgb": str(rgb_path),
                "depth": str(depth_path),
                "canny": str(scene_dir / "canny.png"),
                "is_fallback": is_fallback,
            })

        logger.info(f"  → {len(outputs)} シーンのレンダリング完了")
        return outputs

    async def _stage_realify(self, job_spec: JobSpec, render_outputs: List[dict]) -> List[dict]:
        """
        [ハイブリッド移行対応]
        現在はまだFal.ai等のFLUX APIが未構成のため、実写化をスキップし入力画像をそのままスルーパスします。
        """
        outputs = []
        for i, render in enumerate(render_outputs):
            logger.info(f"  [{i+1}/{len(render_outputs)}] {render['scene_id']} - API実写化(FLUX)モックを通過")
            outputs.append({
                "scene_id": render["scene_id"],
                "image": render["rgb"],
            })
        return outputs

    async def _stage_tts(self, job: JobSpec) -> List[dict]:
        """
        TTSエンジンで台本テキストを音声合成。
        """
        tts = self._get_tts_manager()
        outputs = []

        for i, scene in enumerate(job.scenes):
            logger.info(f"  [{i+1}/{len(job.scenes)}] '{scene.script_text[:30]}...'")

            audio_dir = self.work_dir / f"scene_{i:03d}" / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = str(audio_dir / "voice.wav")

            try:
                result = await tts.synthesize(
                    text=scene.script_text,
                    output_path=audio_path,
                )
                duration = result.get("duration", scene.duration)
            except Exception as e:
                logger.warning(f"  ⚠ TTS失敗 ({scene.scene_id}): {e}")
                duration = scene.duration
                # 404エラーや後の結合エラーを防ぐため、エラー時はダミー(無音)WAVファイルを生成する
                import subprocess
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(duration), "-c:a", "pcm_s16le", audio_path],
                        capture_output=True,
                        check=True
                    )
                except Exception as ffmpeg_e:
                    logger.error(f"ダミーWAVの生成にも失敗しました: {ffmpeg_e}")

            outputs.append({
                "scene_id": scene.scene_id,
                "audio": audio_path,
                "duration": duration,
            })

        logger.info(f"  → {len(outputs)} シーンの音声合成完了")
        return outputs

    async def _upload_file_to_public_url(self, local_path: str) -> str:
        """
        ローカルの画像や音声ファイルを外部API(Kling/Hedra等)へ渡すための公開URLへアップロードする。
        現在は一時的なファイルホスティングとして catbox.moe を使用。
        """
        logger.info(f"  [API準備] ローカルファイルを公開URLへアップロード中...: {local_path}")
        
        import httpx
        url = 'https://catbox.moe/user/api.php'
        
        with open(local_path, 'rb') as f:
            files = {'fileToUpload': (Path(local_path).name, f)}
            data = {'reqtype': 'fileupload'}
            
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, data=data, files=files, timeout=60.0)
                    resp.raise_for_status()
                    public_url = resp.text.strip()
                    if not public_url.startswith("http"):
                        raise ValueError(f"予期しないレスポンス: {public_url}")
                    logger.info(f"  [API準備] アップロード成功: {public_url}")
                    return public_url
                except Exception as e:
                    logger.error(f"ファイルアップロードに失敗しました: {e}")
                    raise

    async def _stage_video(self, job_spec: JobSpec, scene_results: List[dict]) -> List[dict]:
        """
        [ハイブリッド移行] Kling AI API による映像生成 + 商用LipSync
        """
        from src.modules.video_gen.kling import KlingAPIClient
        from src.modules.lipsync.sync_so import LipSyncAPIClient
        try:
            kling_client = KlingAPIClient()
        except ValueError as e:
            logger.warning(f"  ⚠ Kling APIキーが未設定です。ダミーにフォールバックします: {e}")
            kling_client = None

        try:
            lipsync_client = LipSyncAPIClient()
        except ValueError as e:
            logger.warning(f"  ⚠ LipSync APIキーが未設定です。LipSync処理プロセスをスキップします: {e}")
            lipsync_client = None

        outputs = []

        for i, res in enumerate(scene_results):
            img = res.get("image")
            audio = res.get("audio")
            if not img:
                continue

            scene_id = res["scene_id"]
            logger.info(f"  [{i+1}/{len(scene_results)}] {scene_id} の動画・音声合成生成 (商用API)")

            video_dir = self.work_dir / f"scene_{i:03d}" / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            
            video_path = str(video_dir / "clip.mp4")

            duration = res.get("duration", 5.0)
            scene_spec = next((s for s in job_spec.scenes if s.scene_id == scene_id), None)
            kling_prompt = scene_spec.background_prompt if scene_spec and scene_spec.background_prompt else "slow camera pan, subtle natural breathing, realistic movement, highly detailed, cinematic"

            try:
                if kling_client:
                    # 1. 画像の公開URL化
                    public_img_url = await self._upload_file_to_public_url(img)
                    
                    # 2. Kling AI API I2V送信
                    kling_task_id = await kling_client.submit_i2v_task(
                        image_url=public_img_url,
                        prompt=kling_prompt,
                        duration=int(min(5, max(3, duration)))
                    )
                    
                    # 3. Kling AI 動画完成URL取得
                    final_video_url = await kling_client.wait_for_task(kling_task_id, poll_interval_sec=10, timeout_sec=900)
                    
                    # 4. LipSync API に即座にパス（KlingのURLをそのまま流用）
                    if lipsync_client and audio and Path(audio).exists():
                        logger.info(f"  [API中継] Kling動画完了を検知。そのままLipSync APIへ動画URLと音声をパスします。")
                        public_audio_url = await self._upload_file_to_public_url(audio)
                        ls_task_id = await lipsync_client.submit_lipsync_task(final_video_url, public_audio_url)
                        final_video_url = await lipsync_client.wait_for_task(ls_task_id, poll_interval_sec=10, timeout_sec=900)

                    # 5. 完成した100%最終動画のみをローカルにダウンロード
                    import httpx
                    local_video_path = str(video_dir / f"hybrid_final_{scene_id}.mp4")
                    logger.info(f"  [API完了] 最終合成映像をダウンロード中... -> {local_video_path}")
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(final_video_url)
                        with open(local_video_path, "wb") as f:
                            f.write(resp.content)
                            
                    video_path = local_video_path
                else:
                    logger.info(f"  [APIモック] ダミー動画を適用します。")
                    import shutil
                    fallback_candidates = [Path(r"F:\ComfyUI\output\fallback_dummy.mp4")]
                    if fallback_candidates[0].exists():
                        shutil.copy(fallback_candidates[0], video_path)

            except Exception as e:
                logger.error(f"  ❌ 商用API処理エラー ({scene_id}): {e}")
                raise RuntimeError(f"商用API側の処理エラー・タイムアウトが発生しました: {e}")

            outputs.append({
                "scene_id": scene_id,
                "video": video_path,
                "audio": audio,
            })

        logger.info(f"  → {len(outputs)} シーンの商用API動画生成完了")
        return outputs

    async def _stage_compose(self, job: JobSpec, video_outputs: List[dict]) -> Path:
        """
        MoviePy + FFmpeg で全シーンを結合し、BGM・テロップを追加。
        """
        compositor = self._get_compositor()
        output_path = PROJECT_ROOT / job.output_path

        # SRT字幕を生成
        from src.modules.compositor.moviepy_editor.compositor import SubtitleGenerator
        srt_path = str(self.work_dir / "subtitles.srt")
        accumulated_time = 0.0
        srt_scenes = []
        for i, scene in enumerate(job.scenes):
            srt_scenes.append({
                "text": scene.script_text,
                "start": accumulated_time,
                "end": accumulated_time + scene.duration,
            })
            accumulated_time += scene.duration
        SubtitleGenerator.generate_srt(srt_scenes, srt_path)

        # 動画結合
        bg_image_path = getattr(job, "bg_image_path", None)
        if not bg_image_path:
            bg_image_path = str(PROJECT_ROOT / "assets" / "default_bg.jpg")
        
        result = await compositor.compose(
            scene_clips=video_outputs,
            output_path=str(output_path),
            bgm_path=job.bgm_path,
            srt_path=srt_path,
            resolution=job.resolution,
            bg_image_path=bg_image_path
        )

        logger.info(f"  → 最終動画: {result}")
        return Path(result)


# ── CLI エントリポイント ─────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Avatar Video Pipeline - 3Dアバターから実写風AI動画を全自動生成",
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="入力VRMモデルのパス",
    )
    parser.add_argument(
        "--script", "-s",
        type=str,
        help="台本JSONファイルのパス",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output/final.mp4",
        help="出力MP4パス (default: output/final.mp4)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=5.0,
        help="テスト動画の秒数 (default: 5.0)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="テストモードで実行（サンプルデータ使用）",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    settings = load_settings()
    setup_logging(settings.job.log_level)

    logger.info("Avatar Video Pipeline v0.1.0")
    logger.info(f"GPU VRAM制限: {settings.gpu.vram_limit}MB")
    logger.info(f"ComfyUI: {settings.comfyui.base_url}")

    # テストモード: サンプルジョブを生成
    if args.test:
        job = JobSpec(
            avatar_path=args.input or "models/sample_avatar.vrm",
            scenes=[
                SceneSpec(
                    scene_id="test_001",
                    script_text="こんにちは、私はAIが生成したアバターです。",
                    pose="greeting",
                    expression="smile",
                    duration=args.duration,
                ),
            ],
            output_path=args.output,
        )
    elif args.script:
        # 台本JSONから読み込み
        with open(args.script, "r", encoding="utf-8") as f:
            script_data = json.load(f)
        job = JobSpec(
            avatar_path=script_data.get("avatar", args.input or ""),
            scenes=[
                SceneSpec(**s) for s in script_data.get("scenes", [])
            ],
            bgm_path=script_data.get("bgm"),
            output_path=args.output,
        )
    else:
        logger.error("--input または --script を指定してください")
        sys.exit(1)

    pipeline = Pipeline(settings)
    result = await pipeline.run(job)

    if result.success:
        logger.info(f"🎬 完成: {result.output_path} ({result.elapsed_seconds:.1f}秒)")
    else:
        logger.error(f"💥 失敗: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
>>>>>>> master
