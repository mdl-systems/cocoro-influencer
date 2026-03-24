"""cocoro-inf: 企業専属AIインフルエンサー生成CLI

typerによるコマンドラインインターフェース。
各エンジンをCLIから直接実行できる。

使用例:
    cocoro-inf avatar generate --prompt "ビジネススーツの日本人女性" --output ./outputs/avatar.png
"""

import logging
from pathlib import Path

import typer

from src.engines.flux_engine import FluxEngine
from src.engines.manager import EngineManager

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

# サブコマンド: avatar
avatar_app = typer.Typer(
    help="アバター画像生成コマンド",
    no_args_is_help=True,
)
app.add_typer(avatar_app, name="avatar")


@avatar_app.command("generate")
def avatar_generate(
    prompt: str = typer.Option(
        ...,
        "--prompt",
        "-p",
        help="画像生成プロンプト (例: 'ビジネススーツの日本人女性, 30代')",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="出力画像ファイルパス",
    ),
    lora: Path | None = typer.Option(
        None,
        "--lora",
        "-l",
        help="LoRA safetensorsファイルパス (オプション)",
    ),
    width: int = typer.Option(
        1024,
        "--width",
        "-W",
        help="画像幅 (ピクセル)",
    ),
    height: int = typer.Option(
        1024,
        "--height",
        "-H",
        help="画像高さ (ピクセル)",
    ),
    steps: int = typer.Option(
        30,
        "--steps",
        "-s",
        help="推論ステップ数",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        help="ランダムシード (再現性のため)",
    ),
) -> None:
    """FLUX.2 + LoRA でアバター画像を生成する"""
    try:
        # 出力ディレクトリ作成
        output.parent.mkdir(parents=True, exist_ok=True)

        # EngineManager でFluxEngineを使用
        manager = EngineManager()
        flux_engine = FluxEngine()
        manager.register("flux", flux_engine)

        engine = manager.get("flux")

        # 画像生成
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

    except FileNotFoundError as e:
        typer.echo(f"❌ ファイルが見つかりません: {e}", err=True)
        raise typer.Exit(code=1) from e
    except RuntimeError as e:
        typer.echo(f"❌ 実行エラー: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"❌ 予期しないエラーが発生しました: {e}", err=True)
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()
