#!/usr/bin/env python3
"""
Wan2.2 I2V 動画生成スクリプト
アバター画像から体の動きを含む動画を生成し、Wav2Lip でリップシンクを追加する。

使用例:
  python scripts/generate_wan22_video.py \
    --image /data/outputs/cocoro_customer/avatar.png \
    --audio /data/outputs/cocoro_customer/audio.wav \
    --output /data/outputs/cocoro_customer/scene_000_clip.mp4 \
    --guide_scale 7.5
"""

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# パス設定
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WAN22_PYTHON   = "/data/venv/wan2/bin/python"
WAN22_SCRIPT   = "/data/models/Wan2.2-repo/generate.py"
WAN22_CKPT     = "/data/models/Wan2.2/I2V-A14B"
WAV2LIP_PYTHON = "/data/models/Wav2Lip/venv/bin/python"
WAV2LIP_SCRIPT = "/home/cocoro-influencer/scripts/wav2lip_fullbody.py"


def get_audio_duration(audio_path: str) -> float:
    """音声ファイルの長さ（秒）を取得"""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 5.0


def calc_frame_num(duration: float, fps: int = 16, max_frames: int = 129) -> int:
    """音声長から Wan2.2 の 4k+1 フレーム数を計算"""
    raw = int(duration * fps) + 1
    k = max(8, (raw - 1) // 4)
    frames = 4 * k + 1
    if frames > max_frames:
        frames = max_frames
    if frames < raw and frames + 4 <= max_frames:
        frames += 4
    return frames


def run_wan22_i2v(
    image_path: str,
    output_path: str,
    prompt: str,
    frame_num: int,
    guide_scale: float = 7.5,
    size: str = "832*480",
) -> bool:
    """Wan2.2 I2V で体の動きを含む動画を生成"""
    cmd = [
        WAN22_PYTHON, WAN22_SCRIPT,
        "--task", "i2v-A14B",
        "--ckpt_dir", WAN22_CKPT,
        "--image", image_path,
        "--prompt", prompt,
        "--frame_num", str(frame_num),
        "--size", size,
        "--save_file", output_path,
        "--offload_model", "true",
        "--sample_guide_scale", str(guide_scale),
    ]
    logger.info("Wan2.2 I2V 開始: %s → %s (%d frames)", image_path, output_path, frame_num)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Wan2.2 失敗:\n%s", result.stderr[-2000:])
        return False
    logger.info("Wan2.2 I2V 完了: %s", output_path)
    return True


def run_wav2lip(
    video_path: str,
    audio_path: str,
    output_path: str,
    audio_duration: float,
) -> bool:
    """Wav2Lip でリップシンクを追加"""
    cmd = [
        WAV2LIP_PYTHON, WAV2LIP_SCRIPT,
        "--video", video_path,
        "--audio", audio_path,
        "--output", output_path,
        "--audio_duration", str(audio_duration),
    ]
    logger.info("Wav2Lip リップシンク開始: %s", video_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.warning("Wav2Lip 失敗（Wan2.2 動画をそのまま使用）:\n%s", result.stderr[-1000:])
        return False
    logger.info("Wav2Lip 完了: %s", output_path)
    return True


def trim_to_audio(video_path: str, output_path: str, duration: float) -> None:
    """動画を音声長にトリム"""
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        output_path,
    ], capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wan2.2 I2V + Wav2Lip パイプライン")
    parser.add_argument("--image",       required=True,  help="入力アバター画像パス")
    parser.add_argument("--audio",       required=True,  help="入力音声 WAV パス")
    parser.add_argument("--output",      required=True,  help="出力動画パス")
    parser.add_argument("--prompt",      default=(
        "person speaking naturally, subtle arm gestures, "
        "professional presenter, talking to camera, upper body visible"
    ))
    parser.add_argument("--guide_scale", type=float, default=7.5,  help="キャラクター忠実度 (5〜9)")
    parser.add_argument("--size",        default="832*480",         help="動画サイズ")
    parser.add_argument("--no_lipsync",  action="store_true",       help="Wav2Lip をスキップ")
    args = parser.parse_args()

    image_path  = args.image
    audio_path  = args.audio
    output_path = args.output

    # 音声長を取得
    duration = get_audio_duration(audio_path)
    frame_num = calc_frame_num(duration)
    logger.info("音声長: %.2f秒 → %d フレーム", duration, frame_num)

    with tempfile.TemporaryDirectory(prefix="wan22_") as tmpdir:
        tmp_wan = str(Path(tmpdir) / "wan22_raw.mp4")
        tmp_trim = str(Path(tmpdir) / "wan22_trim.mp4")

        # Step 1: Wan2.2 I2V で体の動き生成
        ok = run_wan22_i2v(
            image_path=image_path,
            output_path=tmp_wan,
            prompt=args.prompt,
            frame_num=frame_num,
            guide_scale=args.guide_scale,
            size=args.size,
        )
        if not ok:
            logger.error("Wan2.2 失敗。終了します。")
            sys.exit(1)

        # Step 2: 音声長にトリム
        trim_to_audio(tmp_wan, tmp_trim, duration)

        # Step 3: Wav2Lip でリップシンク追加
        if not args.no_lipsync and Path(WAV2LIP_SCRIPT).exists():
            ok_lip = run_wav2lip(tmp_trim, audio_path, output_path, duration)
            if not ok_lip:
                # フォールバック: トリム済み動画をそのまま使用
                Path(tmp_trim).rename(output_path)
        else:
            Path(tmp_trim).rename(output_path)

    logger.info("✅ 完了: %s", output_path)


if __name__ == "__main__":
    main()
