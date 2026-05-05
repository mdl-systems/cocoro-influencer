#!/usr/bin/env python3
"""liveportrait_inference.py - LivePortrait によるポートレートアニメーション

アバター画像 + 駆動動画 → 体・頭・目の動きが付いたアニメーション動画

使い方:
    /data/venv/liveportrait/bin/python \\
        /home/cocoro-influencer/scripts/liveportrait_inference.py \\
        --source /path/to/avatar.png \\
        --outfile /path/to/output.mp4 \\
        [--duration 8.5] \\
        [--driving /path/to/driving.mp4]
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

LIVEPORTRAIT_DIR = Path("/data/models/LivePortrait")
LIVEPORTRAIT_PY  = Path("/data/venv/liveportrait/bin/python")

# デフォルト駆動動画（LivePortrait 付属サンプル）
DEFAULT_DRIVING_CANDIDATES = [
    LIVEPORTRAIT_DIR / "assets/examples/driving/d0.mp4",
    LIVEPORTRAIT_DIR / "assets/examples/driving/d1.mp4",
    LIVEPORTRAIT_DIR / "assets/examples/driving/d2.mp4",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_default_driving() -> Path | None:
    """デフォルトの駆動動画を探す"""
    for p in DEFAULT_DRIVING_CANDIDATES:
        if p.exists():
            return p
    # assets 以下から任意の .mp4 を探す
    driving_dir = LIVEPORTRAIT_DIR / "assets/examples/driving"
    if driving_dir.exists():
        candidates = sorted(driving_dir.glob("*.mp4"))
        if candidates:
            return candidates[0]
    return None


def loop_video_to_duration(src: Path, dst: Path, duration: float) -> None:
    """動画をループして指定秒数に調整する"""
    src_duration = float(subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)],
        capture_output=True, text=True,
    ).stdout.strip() or "0")

    if src_duration <= 0:
        raise RuntimeError(f"駆動動画の長さが取得できません: {src}")

    # ループ回数（切り上げ）
    import math
    loops = math.ceil(duration / src_duration)
    logger.info("駆動動画をループ: %.1f秒 × %d回 → %.1f秒", src_duration, loops, duration)

    # concat で指定秒数に切り出す
    concat_input = "\n".join([f"file '{src}'" for _ in range(loops)])
    concat_file = dst.parent / "_driving_loop.txt"
    concat_file.write_text(concat_input)

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-t", str(duration),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-an",  # 音声なし
        str(dst),
    ], check=True, capture_output=True)
    concat_file.unlink(missing_ok=True)


def run_liveportrait(
    source: Path,
    driving: Path,
    output: Path,
    flag_relative: bool = True,
    flag_pasteback: bool = True,
) -> bool:
    """LivePortrait 推論を実行する"""
    cmd = [
        str(LIVEPORTRAIT_PY),
        str(LIVEPORTRAIT_DIR / "inference.py"),
        "--source",  str(source),
        "--driving", str(driving),
        "--output",  str(output.parent),  # LivePortrait はディレクトリを指定
        "--flag_write_result",
    ]
    if flag_relative:
        cmd.append("--flag_relative_motion")
    if flag_pasteback:
        cmd.append("--flag_pasteback")

    logger.info("LivePortrait 実行: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(LIVEPORTRAIT_DIR), timeout=600,
    )

    if result.returncode != 0:
        logger.error("LivePortrait 失敗 (code=%d)\nSTDOUT:\n%s\nSTDERR:\n%s",
                     result.returncode, result.stdout[-2000:], result.stderr[-2000:])
        return False

    # LivePortrait が出力したファイルを探してリネーム
    source_stem = source.stem
    driving_stem = driving.stem
    candidates = list(output.parent.glob(f"*{source_stem}*{driving_stem}*.mp4"))
    if not candidates:
        candidates = sorted(output.parent.glob("*.mp4"),
                            key=lambda p: p.stat().st_mtime)

    if not candidates:
        logger.error("LivePortrait: 出力ファイルが見つかりません: %s", output.parent)
        return False

    latest = candidates[-1]
    if latest != output:
        latest.rename(output)
    logger.info("LivePortrait 完了: %s", output.name)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LivePortrait ポートレートアニメーション"
    )
    parser.add_argument("--source",  required=True, help="入力ポートレート画像")
    parser.add_argument("--outfile", required=True, help="出力動画パス")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="出力動画の秒数（0=駆動動画の長さに合わせる）")
    parser.add_argument("--driving", default="",
                        help="駆動動画パス（省略時は自動選択）")
    args = parser.parse_args()

    source  = Path(args.source)
    outfile = Path(args.outfile)

    if not source.exists():
        logger.error("ソース画像が見つかりません: %s", source)
        sys.exit(1)

    # 駆動動画の決定
    if args.driving:
        driving_src = Path(args.driving)
        if not driving_src.exists():
            logger.error("指定した駆動動画が見つかりません: %s", driving_src)
            sys.exit(1)
    else:
        driving_src = find_default_driving()
        if not driving_src:
            logger.error("デフォルト駆動動画が見つかりません。"
                         "--driving で指定するか LivePortrait サンプルを確認してください。")
            sys.exit(1)
    logger.info("駆動動画: %s", driving_src)

    # 必要なら duration に合わせてループ
    if args.duration > 0:
        looped_driving = outfile.parent / f"_driving_{outfile.stem}.mp4"
        loop_video_to_duration(driving_src, looped_driving, args.duration)
        driving = looped_driving
    else:
        driving = driving_src

    # LivePortrait 実行
    ok = run_liveportrait(source=source, driving=driving, output=outfile)

    # 一時ファイル削除
    if args.duration > 0:
        driving.unlink(missing_ok=True)

    if not ok:
        logger.error("LivePortrait 失敗")
        sys.exit(1)

    logger.info("=== LivePortrait 完了 → %s ===", outfile)


if __name__ == "__main__":
    main()
