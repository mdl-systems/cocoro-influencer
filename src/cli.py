"""cocoro-inf: 企業専属AIインフルエンサー生成CLI (Phase 2)

typerによるコマンドラインインターフェース。
Phase 1: avatar generate
Phase 2: voice generate / talking-head generate / cinematic generate / compose

使用例:
    cocoro-inf avatar generate --prompt "ビジネススーツの日本人女性" --output ./outputs/avatar.png
    cocoro-inf voice generate --text "こんにちは" --output ./outputs/voice.wav
    cocoro-inf talking-head generate --image avatar.png --audio voice.wav --output clip.mp4
    cocoro-inf cinematic generate --image avatar.png --prompt "オフィスで" --output scene.mp4
    cocoro-inf compose --clips clip.mp4 scene.mp4 --format youtube --output final.mp4
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

app.add_typer(avatar_app, name="avatar")
app.add_typer(voice_app, name="voice")
app.add_typer(talking_head_app, name="talking-head")
app.add_typer(cinematic_app, name="cinematic")


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


if __name__ == "__main__":
    app()
