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

app.add_typer(avatar_app, name="avatar")
app.add_typer(voice_app, name="voice")
app.add_typer(talking_head_app, name="talking-head")
app.add_typer(cinematic_app, name="cinematic")
app.add_typer(script_app, name="script")
app.add_typer(pipeline_app, name="pipeline")


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


if __name__ == "__main__":
    app()
