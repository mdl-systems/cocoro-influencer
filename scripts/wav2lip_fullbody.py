#!/usr/bin/env python3
"""wav2lip_fullbody.py: 高品質リップシンク v4.0

## v4.0 設計方針 - シンプル直接方式
  クロップ→オーバーレイ方式を廃止。
  動画全体を処理サイズにリサイズし Wav2Lip を直接適用する。
  → オーバーレイ継ぎ目ゼロ, 崩れなし, 自然な仕上がり

## 実行環境
    /data/models/Wav2Lip/venv/bin/python

## 使い方
    /data/models/Wav2Lip/venv/bin/python \\
        /home/cocoro-influencer/scripts/wav2lip_fullbody.py \\
        --face  /path/to/video.mp4 \\
        --audio /path/to/voice.wav \\
        --outfile /path/to/output.mp4
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

# Wav2Lip のパス設定
WAV2LIP_DIR = Path("/data/models/Wav2Lip")
_NON_GAN = WAV2LIP_DIR / "checkpoints/wav2lip.pth"
_GAN     = WAV2LIP_DIR / "checkpoints/wav2lip_gan.pth"
WAV2LIP_CHECKPOINT = (
    _NON_GAN if _NON_GAN.exists() and _NON_GAN.stat().st_size > 1_000_000 else _GAN
)
WAV2LIP_TEMP_DIR = WAV2LIP_DIR / "temp"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# ユーティリティ
# ──────────────────────────────────────────────────────────────

def run_ffmpeg(args: list[str]) -> None:
    """FFmpegコマンドを実行する。失敗時は RuntimeError"""
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg stderr:\n%s", result.stderr[-2000:])
        raise RuntimeError(f"FFmpeg失敗 (code={result.returncode}): {result.stderr[-300:]}")


def get_video_info(video_path: Path) -> dict:
    """動画の詳細情報を取得する"""
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(video_path),
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            fps_str = s.get("r_frame_rate", "25/1")
            num, den = fps_str.split("/")
            return {
                "width":    s["width"],
                "height":   s["height"],
                "fps":      float(num) / float(den),
                "duration": float(data.get("format", {}).get("duration", 0)),
            }
    raise RuntimeError(f"動画情報取得失敗: {video_path}")


# ──────────────────────────────────────────────────────────────
# メイン処理 (v4.0 シンプル直接方式)
# ──────────────────────────────────────────────────────────────

def lipsync_fullbody(
    face_video: Path,
    audio: Path,
    output: Path,
    processing_width: int = 480,  # Wav2Lip処理幅 (px)
    output_crf: int = 18,         # 出力品質 (18=高品質)
) -> bool:
    """動画全体にWav2Lipを直接適用するシンプル方式 (v4.0)

    クロップ・オーバーレイなし → 継ぎ目ゼロ・崩れなし。
    動画全体を処理サイズにリサイズして Wav2Lip を適用し
    最終的に元の解像度に戻す。

    Args:
        face_video:        入力動画
        audio:             音声 WAV ファイル
        output:            出力ファイルパス
        processing_width:  Wav2Lip処理幅 (縦動画は幅ベース)
        output_crf:        FFmpeg CRF値

    Returns:
        True=成功, False=失敗
    """
    logger.info("=== Wav2Lip リップシンク v4.0 (直接方式) ===")
    logger.info("  入力  : %s", face_video.name)
    logger.info("  音声  : %s", audio.name)
    logger.info("  出力  : %s", output.name)
    logger.info("  モデル: %s", WAV2LIP_CHECKPOINT.name)

    tmp = output.parent
    WAV2LIP_TEMP_DIR.mkdir(exist_ok=True)

    # Step 1: 動画情報取得
    info = get_video_info(face_video)
    vid_w, vid_h = info["width"], info["height"]
    logger.info("Step1: 動画情報 %dx%d @%.2ffps", vid_w, vid_h, info["fps"])

    # Step 2: Wav2Lip処理サイズを計算
    # 縦動画(9:16)も横動画も幅ベースでスケール
    # Wav2Lip は幅・高さが4の倍数であること
    if vid_w <= processing_width:
        # すでに小さい → 偶数に丸めるだけ
        proc_w = vid_w - (vid_w % 4)
        proc_h = vid_h - (vid_h % 4)
    else:
        proc_w = processing_width - (processing_width % 4)
        proc_h = int(proc_w * vid_h / vid_w)
        proc_h -= proc_h % 4

    logger.info("Step2: 処理サイズ %dx%d → %dx%d", vid_w, vid_h, proc_w, proc_h)

    # Step 3: 処理サイズにリサイズ (音声なし)
    needs_resize = (proc_w != vid_w or proc_h != vid_h)
    if needs_resize:
        proc_path = tmp / f"_v4_proc_{output.stem}.mp4"
        logger.info("Step3: Wav2Lip処理用にリサイズ...")
        run_ffmpeg([
            "-i", str(face_video),
            "-vf", f"scale={proc_w}:{proc_h}:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-an",
            str(proc_path),
        ])
    else:
        proc_path = face_video

    # Step 4: Wav2Lip 実行 (直接方式)
    # pads = [top, bottom, left, right]
    # bottom=20: 口下部を少し広めにカバー
    wav2lip_out = tmp / f"_v4_lipsync_{output.stem}.mp4"
    logger.info("Step4: Wav2Lip 実行 (直接方式, smoothing=ON)...")

    w2l_result = subprocess.run([
        sys.executable,
        str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path",    str(WAV2LIP_CHECKPOINT),
        "--face",               str(proc_path),
        "--audio",              str(audio),
        "--outfile",            str(wav2lip_out),
        "--pads",    "0", "20", "0", "0",   # top/bottom/left/right padding
        "--resize_factor",      "1",          # リサイズは済み
        "--face_det_batch_size", "4",         # 精度優先 (低バッチ)
        "--wav2lip_batch_size",  "64",        # バランス設定
        # --nosmooth は使わない: GAN モデルはスムージングあり = 自然な口の動き
    ], capture_output=True, text=True, cwd=str(WAV2LIP_DIR), timeout=600)

    # proc_pathがリサイズした中間ファイルなら削除
    if needs_resize and proc_path != face_video:
        proc_path.unlink(missing_ok=True)

    if w2l_result.returncode != 0 or not wav2lip_out.exists():
        logger.warning(
            "Wav2Lip失敗 (code=%d)\n=== STDOUT ===\n%s\n=== STDERR ===\n%s",
            w2l_result.returncode,
            w2l_result.stdout[-1000:],
            w2l_result.stderr[-2000:],
        )
        return False

    logger.info("Step4完了: Wav2Lip成功")

    # Step 5: 元の解像度に戻して音声合成
    logger.info("Step5: 元解像度 %dx%d に復元 + 音声合成 (CRF=%d)...", vid_w, vid_h, output_crf)
    run_ffmpeg([
        "-i", str(wav2lip_out),
        "-i", str(audio),
        "-vf", f"scale={vid_w}:{vid_h}:flags=lanczos,setsar=1,format=yuv420p",
        "-c:v", "libx264",
        "-crf", str(output_crf),
        "-preset", "medium",
        "-map", "0:v",
        "-map", "1:a",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ])

    wav2lip_out.unlink(missing_ok=True)
    logger.info("=== Wav2Lip v4.0 完了 → %s ===", output)
    return True


# ──────────────────────────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wav2Lip リップシンク v4.0 (直接方式・オーバーレイなし)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--face",              required=True, help="入力動画パス")
    parser.add_argument("--audio",             required=True, help="音声 WAV ファイルパス")
    parser.add_argument("--outfile",           required=True, help="出力動画パス")
    parser.add_argument("--processing_width",  type=int, default=480,
                        help="Wav2Lip処理幅 (px) [デフォルト: 480]")
    parser.add_argument("--crf",               type=int, default=18,
                        help="出力CRF値 [デフォルト: 18]")
    args = parser.parse_args()

    logger.info("wav2lip_fullbody.py v4.0 起動")
    logger.info("  使用チェックポイント: %s", WAV2LIP_CHECKPOINT.name)

    success = lipsync_fullbody(
        face_video=Path(args.face),
        audio=Path(args.audio),
        output=Path(args.outfile),
        processing_width=args.processing_width,
        output_crf=args.crf,
    )

    if not success:
        logger.error("リップシンク失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
