#!/usr/bin/env python3
"""sadtalker_inference.py - SadTalker リップシンク推論スクリプト

画像 + 音声 → リップシンク済み動画

Wav2Lipと異なり、言語非依存の音響特徴量から口形を生成するため
日本語の読み上げでも正確なリップシンクが可能。

使い方:
    /data/venv/sadtalker/bin/python \\
        /home/cocoro-influencer/scripts/sadtalker_inference.py \\
        --image  /path/to/portrait.png \\
        --audio  /path/to/voice.wav \\
        --outfile /path/to/output.mp4 \\
        [--width 512] [--height 512] [--enhancer gfpgan]
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

SADTALKER_DIR  = Path("/data/models/SadTalker")
SADTALKER_PY   = Path("/data/venv/sadtalker/bin/python")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_audio_duration(audio_path: Path) -> float:
    """音声ファイルの長さ(秒)を取得"""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(audio_path)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))


def run_sadtalker(
    image_path: Path,
    audio_path: Path,
    result_dir: Path,
    size: int = 512,
    still: bool = False,
    enhancer: str | None = "gfpgan",
    preprocess: str = "full",
) -> Path | None:
    """SadTalker 推論を実行して生成された動画パスを返す"""
    result_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(SADTALKER_PY),
        str(SADTALKER_DIR / "inference.py"),
        "--driven_audio",  str(audio_path),
        "--source_image",  str(image_path),
        "--result_dir",    str(result_dir),
        "--preprocess",    preprocess,      # full: 全顔処理
        "--size",          str(size),       # 256 or 512
        "--batch_size",    "2",
    ]

    if still:
        cmd.append("--still")              # 頭の動きを最小化

    if enhancer:
        cmd += ["--enhancer", enhancer]    # gfpgan: 顔品質向上

    logger.info("SadTalker 推論開始 (size=%d, enhancer=%s, still=%s)",
                size, enhancer, still)
    logger.info("コマンド: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=str(SADTALKER_DIR),
        timeout=900,  # 最大15分
    )

    if result.returncode != 0:
        logger.error("SadTalker失敗 (code=%d):\nSTDOUT:\n%s\nSTDERR:\n%s",
                     result.returncode,
                     result.stdout[-2000:],
                     result.stderr[-2000:])
        return None

    # 生成された .mp4 を検索
    generated = sorted(result_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not generated:
        logger.error("SadTalker: 出力 .mp4 が見つかりません: %s", result_dir)
        return None

    logger.info("SadTalker 完了: %s", generated[-1])
    return generated[-1]


def scale_video(
    src: Path,
    dst: Path,
    width: int,
    height: int,
    crf: int = 18,
) -> None:
    """動画を指定サイズにスケール + 高品質エンコード"""
    # 比率を保ちながらのスケールは fit-in で対応
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,format=yuv420p"
        ),
        "-c:v", "libx264",
        "-crf",    str(crf),
        "-preset", "medium",
        "-movflags", "+faststart",
    ], check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SadTalker リップシンク推論 (日本語対応・言語非依存)"
    )
    parser.add_argument("--image",    required=True, help="入力ポートレート画像")
    parser.add_argument("--audio",    required=True, help="音声 WAV ファイル")
    parser.add_argument("--outfile",  required=True, help="出力動画パス")
    parser.add_argument("--width",    type=int, default=512, help="出力幅 [512]")
    parser.add_argument("--height",   type=int, default=512, help="出力高さ [512]")
    parser.add_argument("--size",     type=int, default=512, help="SadTalker 内部サイズ (256/512) [512]")
    parser.add_argument("--still",    action="store_true", help="頭の動きを最小化")
    parser.add_argument("--enhancer", default="gfpgan",
                        help="顔品質向上 (gfpgan / none) [gfpgan]")
    parser.add_argument("--preprocess", default="full",
                        help="前処理モード (full/crop/resize) [full]")
    parser.add_argument("--crf",      type=int, default=18, help="出力 CRF [18]")
    args = parser.parse_args()

    image_path  = Path(args.image)
    audio_path  = Path(args.audio)
    outfile     = Path(args.outfile)
    enhancer    = args.enhancer if args.enhancer != "none" else None

    logger.info("sadtalker_inference.py 起動")
    logger.info("  入力画像: %s", image_path)
    logger.info("  音声    : %s", audio_path)
    logger.info("  出力    : %s", outfile)

    if not image_path.exists():
        logger.error("画像ファイルが見つかりません: %s", image_path)
        sys.exit(1)
    if not audio_path.exists():
        logger.error("音声ファイルが見つかりません: %s", audio_path)
        sys.exit(1)

    # 音声長を確認
    duration = get_audio_duration(audio_path)
    logger.info("  音声長: %.1f秒", duration)

    # SadTalker 出力用一時ディレクトリ
    tmp_dir = outfile.parent / f"_sadtalker_tmp_{outfile.stem}"
    try:
        # SadTalker 実行
        generated = run_sadtalker(
            image_path  = image_path,
            audio_path  = audio_path,
            result_dir  = tmp_dir,
            size        = args.size,
            still       = args.still,
            enhancer    = enhancer,
            preprocess  = args.preprocess,
        )

        if generated is None:
            logger.error("SadTalker 生成失敗")
            sys.exit(1)

        # スケール調整して最終出力
        if args.width != args.size or args.height != args.size:
            logger.info("スケール調整: %dx%d → %dx%d", args.size, args.size, args.width, args.height)
            scale_video(generated, outfile, args.width, args.height, args.crf)
        else:
            shutil.copy(str(generated), str(outfile))

        logger.info("=== SadTalker 完了 → %s ===", outfile)

    finally:
        # 一時ファイル削除
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
