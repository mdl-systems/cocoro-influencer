#!/usr/bin/env python3
"""wav2lip_fullbody.py: 全身動画対応リップシンク

通常の Wav2Lip は顔が小さすぎる全身ショットで検出に失敗する。
このスクリプトは以下の手順で全身動画に対応する:

  1. 動画の最初の数フレームから顔領域(bbox)を検出
  2. 顔周囲をパディング付きでクロップし、Wav2Lip が検出できる大きさにスケールアップ
  3. クロップ済み動画に標準 Wav2Lip を適用
  4. リップシンク済み顔クロップを元サイズに戻して元動画にオーバーレイ

【実行環境】
    Wav2Lip の venv に OpenCV + face_detection が含まれるため、そのvenvで実行すること。

【使い方】
    /data/models/Wav2Lip/venv/bin/python \\
        /home/cocoro-influencer/scripts/wav2lip_fullbody.py \\
        --face  /path/to/kling_video.mp4 \\
        --audio /path/to/voice.wav \\
        --outfile /path/to/output.mp4
"""

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

# Wav2Lip のパス設定
WAV2LIP_DIR = Path("/data/models/Wav2Lip")
WAV2LIP_CHECKPOINT = WAV2LIP_DIR / "checkpoints/wav2lip_gan.pth"
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
    cmd = ["ffmpeg"] + args
    logger.debug("FFmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg stderr:\n%s", result.stderr[-2000:])
        raise RuntimeError(
            f"FFmpeg失敗 (code={result.returncode}): {result.stderr[-300:]}"
        )


def get_video_dimensions(video_path: Path) -> tuple[int, int, float]:
    """動画の (幅, 高さ, fps) を取得する"""
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", str(video_path),
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            fps_str = s.get("r_frame_rate", "24/1")
            num, den = fps_str.split("/")
            return s["width"], s["height"], float(num) / float(den)
    raise RuntimeError(f"動画情報取得失敗: {video_path}")


# ──────────────────────────────────────────────────────────────
# 顔検出
# ──────────────────────────────────────────────────────────────

def detect_face_region_haar(video_path: Path) -> tuple[int, int, int, int] | None:
    """OpenCV Haar Cascade で顔領域を検出 (x, y, w, h)"""
    import cv2

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(str(video_path))
    best_face = None
    frame_idx = 0

    # 最大20フレームをサンプリング（均等間隔）
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 60
    sample_step = max(1, total_frames // 20)

    while frame_idx < min(total_frames, 120):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(20, 20),
        )
        if len(faces) > 0:
            # 最大面積の顔
            best_face = max(faces, key=lambda f: f[2] * f[3])
            logger.info("顔検出 (Haar): frame=%d bbox=%s", frame_idx, best_face.tolist())
            break

        frame_idx += sample_step

    cap.release()
    return tuple(best_face.tolist()) if best_face is not None else None


def detect_face_region_deep(video_path: Path) -> tuple[int, int, int, int] | None:
    """face_detection モジュール（Wav2Lip付属）で顔領域を検出"""
    try:
        sys.path.insert(0, str(WAV2LIP_DIR))
        import face_detection

        # 最初のフレームを取得
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        frames = []
        for _ in range(5):
            ret, frame = cap.read()
            if ret:
                frames.append(frame[:, :, ::-1])  # BGR→RGB
        cap.release()

        if not frames:
            return None

        detector = face_detection.FaceAlignment(
            face_detection.LandmarksType._2D,
            flip_input=False,
            device="cuda",
        )
        predictions = detector.get_detections_for_batch([frames[0]])
        if not predictions or predictions[0] is None:
            return None

        rect = predictions[0][0]
        x1, y1, x2, y2 = [int(v) for v in rect[:4]]
        return (x1, y1, x2 - x1, y2 - y1)

    except Exception as e:
        logger.warning("deep face detection 失敗: %s", e)
        return None


def detect_face_region(video_path: Path) -> tuple[int, int, int, int] | None:
    """顔領域を検出する。deep→Haar の優先順で試みる"""
    # まず Wav2Lip 付属の深層学習モデルで試みる
    region = detect_face_region_deep(video_path)
    if region is not None:
        logger.info("顔検出 (deep): bbox=%s", region)
        return region

    # フォールバック: Haar Cascade
    region = detect_face_region_haar(video_path)
    if region is not None:
        return region

    return None


# ──────────────────────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────────────────────

def lipsync_fullbody(
    face_video: Path,
    audio: Path,
    output: Path,
    padding: int = 80,
    lipsync_scale: int = 720,
) -> bool:
    """全身動画のリップシンク (顔クロップ → Wav2Lip → 元サイズにオーバーレイ)

    Args:
        face_video: Kling AI が生成した全身動画 (音声なし可)
        audio: 音声 WAV ファイル
        output: 出力ファイルパス
        padding: 顔BBox周囲のパディング (px)
        lipsync_scale: Wav2Lip 入力にスケールアップする幅 (px)

    Returns:
        True=成功, False=顔検出失敗など (呼び出し元でスキップ処理すること)
    """
    tmp = output.parent

    # Step 1: 顔領域検出
    logger.info("Step1: 顔領域を検出中 (%s)...", face_video.name)
    face_region = detect_face_region(face_video)
    if face_region is None:
        logger.warning("顔が検出できませんでした → 全身Wav2Lipをスキップ")
        return False

    fx, fy, fw, fh = face_region
    vid_w, vid_h, vid_fps = get_video_dimensions(face_video)

    # クロップ領域 (パディング + 境界チェック + 偶数アライメント)
    cx = max(0, fx - padding)
    cy = max(0, fy - padding)
    cw = min(vid_w - cx, fw + padding * 2)
    ch = min(vid_h - cy, fh + padding * 2)
    cw -= cw % 2
    ch -= ch % 2

    logger.info(
        "Step1完了: bbox=(%d,%d,%d,%d) crop=(%d,%d,%d,%d) @%dx%d",
        fx, fy, fw, fh, cx, cy, cw, ch, vid_w, vid_h,
    )

    # Step 2: 顔クロップ動画を作成し Wav2Lip が検出できる大きさにスケールアップ
    face_crop_path = tmp / f"_wb_crop_{output.stem}.mp4"
    lipsync_h = int(lipsync_scale * ch / cw) if cw > 0 else lipsync_scale
    lipsync_h -= lipsync_h % 2

    logger.info("Step2: 顔クロップ → %dx%d ...", lipsync_scale, lipsync_h)
    run_ffmpeg([
        "-i", str(face_video),
        "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale={lipsync_scale}:{lipsync_h}",
        "-c:v", "libx264", "-an",
        str(face_crop_path), "-y",
    ])

    # Step 3: Wav2Lip 実行
    face_lipsync_path = tmp / f"_wb_lipsync_{output.stem}.mp4"
    logger.info("Step3: Wav2Lip 実行中...")
    WAV2LIP_TEMP_DIR.mkdir(exist_ok=True)
    w2l_result = subprocess.run([
        sys.executable,
        str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path", str(WAV2LIP_CHECKPOINT),
        "--face", str(face_crop_path),
        "--audio", str(audio),
        "--outfile", str(face_lipsync_path),
        "--pads", "0", "25", "0", "0",   # 下に25px余白 → 顎・唇全体をカバー
        "--resize_factor", "1",
        "--nosmooth",                      # ブラーを無効化 → 唇のシャープさ向上
    ], capture_output=True, text=True, cwd=str(WAV2LIP_DIR))

    if w2l_result.returncode != 0 or not face_lipsync_path.exists():
        logger.warning("Wav2Lip失敗 (code=%d):\n%s", w2l_result.returncode, w2l_result.stderr[-500:])
        for p in [face_crop_path]:
            p.unlink(missing_ok=True)
        return False

    logger.info("Step3完了: Wav2Lip 成功")

    # Step 4: リップシンク済み顔を元のクロップサイズに戻す
    face_restored_path = tmp / f"_wb_restored_{output.stem}.mp4"
    logger.info("Step4: 元サイズに縮小 → %dx%d ...", cw, ch)
    run_ffmpeg([
        "-i", str(face_lipsync_path),
        "-vf", f"scale={cw}:{ch},setsar=1",
        "-c:v", "libx264", "-an",
        str(face_restored_path), "-y",
    ])

    # Step 5: 元動画にオーバーレイして完成
    logger.info("Step5: 元動画にオーバーレイ (offset x=%d y=%d) ...", cx, cy)
    run_ffmpeg([
        "-i", str(face_video),
        "-i", str(face_restored_path),
        "-filter_complex",
        f"[0:v][1:v]overlay={cx}:{cy}[outv]",
        "-map", "[outv]",
        "-c:v", "libx264", "-an",
        "-movflags", "+faststart",
        str(output), "-y",
    ])

    # クリーンアップ
    for p in [face_crop_path, face_lipsync_path, face_restored_path]:
        p.unlink(missing_ok=True)

    logger.info("全身Wav2Lip完了 → %s", output)
    return True


# ──────────────────────────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="全身動画対応 Wav2Lip リップシンク")
    parser.add_argument("--face", required=True, help="入力動画パス (全身ショット)")
    parser.add_argument("--audio", required=True, help="音声 WAV ファイルパス")
    parser.add_argument("--outfile", required=True, help="出力動画パス")
    parser.add_argument("--padding", type=int, default=100, help="顔BBox パディング (px)")
    parser.add_argument("--lipsync_scale", type=int, default=720, help="Wav2Lip 処理解像度幅 (px)")
    args = parser.parse_args()

    success = lipsync_fullbody(
        face_video=Path(args.face),
        audio=Path(args.audio),
        output=Path(args.outfile),
        padding=args.padding,
        lipsync_scale=args.lipsync_scale,
    )

    if not success:
        logger.error("リップシンク失敗: 元動画をそのまま使用してください")
        sys.exit(1)


if __name__ == "__main__":
    main()
