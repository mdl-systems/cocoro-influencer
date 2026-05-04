#!/usr/bin/env python3
"""wav2lip_fullbody.py: 高品質リップシンク (全身・上半身対応) v3.0

## 品質改善のポイント

### v3.0 改善内容
  1. --nosmooth 追加: スムージング無効 → フレーム単位の正確な口形同期
  2. パディング拡大: pad_bottom 0.15→0.25, 上方向 0.05 追加
  3. padding_ratio デフォルト: 0.35→0.45 (顔領域を広くカバー)

### v2.0 改善内容 (継続)
  1. 解像度向上: lipsync_scale 720 (顔検出精度が大幅向上)
  2. パディング動的計算: 顔サイズに応じてパディングを自動調整
  3. Wav2Lipパラメータ最適化: wav2lip_batch_size=128
  4. 出力品質向上: CRF18 (高品質エンコード)
  5. フレームレート保持: 元動画のFPSを維持
  6. 複数フレームサンプリングで顔BBox安定化 (中央値を使用)

## 実行環境
    Wav2Lip の venv で実行すること (face_detection パッケージが必要)

## 使い方
    /data/models/Wav2Lip/venv/bin/python \\
        /home/cocoro-influencer/scripts/wav2lip_fullbody.py \\
        --face  /path/to/video.mp4 \\
        --audio /path/to/voice.wav \\
        --outfile /path/to/output.mp4 \\
        [--lipsync_scale 720] \\
        [--padding_ratio 0.45]
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
# wav2lip.pth (非GAN) があれば優先、なければ wav2lip_gan.pth を使用
_NON_GAN = WAV2LIP_DIR / "checkpoints/wav2lip.pth"
_GAN     = WAV2LIP_DIR / "checkpoints/wav2lip_gan.pth"
WAV2LIP_CHECKPOINT = _NON_GAN if _NON_GAN.exists() and _NON_GAN.stat().st_size > 1_000_000 else _GAN
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
    logger.debug("FFmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg stderr:\n%s", result.stderr[-2000:])
        raise RuntimeError(
            f"FFmpeg失敗 (code={result.returncode}): {result.stderr[-300:]}"
        )


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
            fps = float(num) / float(den)
            return {
                "width": s["width"],
                "height": s["height"],
                "fps": fps,
                "nb_frames": int(s.get("nb_frames", 0)),
                "duration": float(data.get("format", {}).get("duration", 0)),
            }
    raise RuntimeError(f"動画情報取得失敗: {video_path}")


# ──────────────────────────────────────────────────────────────
# 顔検出 (安定化版)
# ──────────────────────────────────────────────────────────────

def detect_face_region_deep_stable(
    video_path: Path,
    n_samples: int = 10,
) -> tuple[int, int, int, int] | None:
    """複数フレームをサンプリングして中央値BBoxを返す (安定版)

    Returns:
        (x, y, w, h) or None
    """
    try:
        sys.path.insert(0, str(WAV2LIP_DIR))
        import face_detection
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 100
        step  = max(1, total // n_samples)

        detector = face_detection.FaceAlignment(
            face_detection.LandmarksType._2D,
            flip_input=False,
            device="cuda",
        )

        bboxes: list[tuple[int,int,int,int]] = []
        for idx in range(0, min(total, n_samples * step), step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            rgb = frame[:, :, ::-1]  # BGR→RGB
            preds = detector.get_detections_for_batch([rgb])
            if preds and preds[0] is not None and len(preds[0]) > 0:
                x1, y1, x2, y2 = [int(v) for v in preds[0][0][:4]]
                bboxes.append((x1, y1, x2 - x1, y2 - y1))
        cap.release()

        if not bboxes:
            return None

        # 中央値で安定化
        xs = sorted(b[0] for b in bboxes)
        ys = sorted(b[1] for b in bboxes)
        ws = sorted(b[2] for b in bboxes)
        hs = sorted(b[3] for b in bboxes)
        mid = len(bboxes) // 2
        result = (xs[mid], ys[mid], ws[mid], hs[mid])
        logger.info("顔検出 (deep/stable, %d frames): bbox=%s", len(bboxes), result)
        return result

    except Exception as e:
        logger.warning("deep face detection 失敗: %s", e)
        return None


def detect_face_region_haar(video_path: Path, n_samples: int = 10) -> tuple[int, int, int, int] | None:
    """OpenCV Haar Cascade で顔領域を検出 (複数フレーム中央値)"""
    import cv2
    import numpy as np

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 100
    step  = max(1, total // n_samples)
    bboxes = []

    for idx in range(0, min(total, n_samples * step), step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=3, minSize=(20, 20),
        )
        if len(faces) > 0:
            best = max(faces, key=lambda f: f[2] * f[3])
            bboxes.append(tuple(best.tolist()))
    cap.release()

    if not bboxes:
        return None

    xs = sorted(b[0] for b in bboxes)
    ys = sorted(b[1] for b in bboxes)
    ws = sorted(b[2] for b in bboxes)
    hs = sorted(b[3] for b in bboxes)
    mid = len(bboxes) // 2
    result = (xs[mid], ys[mid], ws[mid], hs[mid])
    logger.info("顔検出 (Haar/stable, %d frames): bbox=%s", len(bboxes), result)
    return result


def detect_face_region(video_path: Path) -> tuple[int, int, int, int] | None:
    """顔領域を検出する。deep→Haar の優先順で試みる"""
    region = detect_face_region_deep_stable(video_path)
    if region is not None:
        return region
    logger.info("deep検出失敗 → Haar Cascade にフォールバック")
    return detect_face_region_haar(video_path)


# ──────────────────────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────────────────────

def lipsync_fullbody(
    face_video: Path,
    audio: Path,
    output: Path,
    lipsync_scale: int = 720,    # v2: 480→720 (顔検出精度向上)
    padding_ratio: float = 0.45,  # v3: 0.35→0.45 (顔領域を広くカバー)
    output_crf: int = 18,         # 出力品質 (18=高品質)
) -> bool:
    """全身動画の高品質リップシンク

    Args:
        face_video: 入力動画
        audio: 音声 WAV ファイル
        output: 出力ファイルパス
        lipsync_scale: Wav2Lip処理の幅 (px). 720推奨
        padding_ratio: 顔BBox周囲のパディング (顔幅に対する比率)
        output_crf: FFmpeg CRF値 (18=高品質, 23=標準)

    Returns:
        True=成功, False=失敗
    """
    logger.info("=== 高品質リップシンク開始 v3.0 ===")
    logger.info("  入力  : %s", face_video.name)
    logger.info("  音声  : %s", audio.name)
    logger.info("  出力  : %s", output.name)
    logger.info("  モデル: %s", WAV2LIP_CHECKPOINT.name)
    logger.info("  スケール: %d, padding_ratio: %.2f, CRF: %d",
                lipsync_scale, padding_ratio, output_crf)

    tmp = output.parent

    # Step 1: 動画情報取得
    info = get_video_info(face_video)
    vid_w, vid_h, vid_fps = info["width"], info["height"], info["fps"]
    logger.info("Step1: 動画情報 %dx%d @%.2ffps", vid_w, vid_h, vid_fps)

    # Step 2: 顔領域検出 (安定版・複数フレーム中央値)
    logger.info("Step2: 顔領域検出 (複数フレームサンプリング)...")
    face_region = detect_face_region(face_video)
    if face_region is None:
        logger.warning("顔が検出できませんでした → Wav2Lip を直接適用 (標準モード)")
        return _lipsync_direct(face_video, audio, output, vid_w, vid_h, lipsync_scale, output_crf)

    fx, fy, fw, fh = face_region

    # パディングを顔サイズに比例して設定 (動的)
    pad_x      = int(fw * padding_ratio)
    pad_y      = int(fh * padding_ratio)
    pad_bottom = int(fh * (padding_ratio + 0.15))  # 口の下を少し多めに

    cx = max(0, fx - pad_x)
    cy = max(0, fy - pad_y)
    cw = min(vid_w - cx, fw + pad_x * 2)
    ch = min(vid_h - cy, fh + pad_y + pad_bottom)
    cw -= cw % 2
    ch -= ch % 2

    logger.info(
        "Step2完了: face=(%d,%d,%d,%d) crop=(%d,%d,%d,%d) pad=(x=%d y=%d bot=%d)",
        fx, fy, fw, fh, cx, cy, cw, ch, pad_x, pad_y, pad_bottom,
    )

    # Step 3: 顔クロップ動画を Wav2Lip が検出できる解像度にスケールアップ
    face_crop_path = tmp / f"_wb_crop_{output.stem}.mp4"
    scale_h = int(lipsync_scale * ch / cw) if cw > 0 else lipsync_scale
    scale_h -= scale_h % 2

    logger.info("Step3: 顔クロップ → %dx%d ...", lipsync_scale, scale_h)
    run_ffmpeg([
        "-i", str(face_video),
        "-vf", (
            f"crop={cw}:{ch}:{cx}:{cy},"
            f"scale={lipsync_scale}:{scale_h}:flags=lanczos,"  # Lanczos補間で高品質スケール
            "format=yuv420p"
        ),
        "-c:v", "libx264",
        "-crf", "16",          # クロップ段階は高品質を維持
        "-preset", "fast",
        "-an",
        str(face_crop_path),
    ])

    # Wav2Lip パディング設定: 顔下部を十分確保
    # pads = [top, bottom, left, right]
    # scale後の顔サイズに基づいて計算
    scale_ratio    = lipsync_scale / cw if cw > 0 else 1.0
    w2l_pad_bottom = max(30, int(fh * 0.25 * scale_ratio))  # v3: 0.15→0.25 (口周辺を広くカバー)
    w2l_pad_top    = max(0,  int(fh * 0.05 * scale_ratio))  # 少し上も確保

    # Step 4: Wav2Lip 実行
    face_lipsync_path = tmp / f"_wb_lipsync_{output.stem}.mp4"
    logger.info("Step4: Wav2Lip 実行 (batch=128, pad_top=%d pad_bot=%d, nosmooth=True)...",
                w2l_pad_top, w2l_pad_bottom)
    WAV2LIP_TEMP_DIR.mkdir(exist_ok=True)

    w2l_result = subprocess.run([
        sys.executable,
        str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path",   str(WAV2LIP_CHECKPOINT),
        "--face",              str(face_crop_path),
        "--audio",             str(audio),
        "--outfile",           str(face_lipsync_path),
        "--pads",   str(w2l_pad_top), str(w2l_pad_bottom), "0", "0",
        "--resize_factor",     "1",
        "--face_det_batch_size",  "16",
        "--wav2lip_batch_size",   "128",
        "--nosmooth",              # v3: スムージング無効 = フレーム単位の正確な口形同期
    ], capture_output=True, text=True, cwd=str(WAV2LIP_DIR), timeout=600)

    if w2l_result.returncode != 0 or not face_lipsync_path.exists():
        logger.warning(
            "Wav2Lip失敗 (code=%d):\nSTDOUT: %s\nSTDERR: %s",
            w2l_result.returncode,
            w2l_result.stdout[-500:],
            w2l_result.stderr[-1000:],
        )
        face_crop_path.unlink(missing_ok=True)
        return False

    logger.info("Step4完了: Wav2Lip成功")

    # Step 5: リップシンク済み顔を元のクロップサイズに戻す
    face_restored_path = tmp / f"_wb_restored_{output.stem}.mp4"
    logger.info("Step5: 元サイズに縮小 → %dx%d ...", cw, ch)
    run_ffmpeg([
        "-i", str(face_lipsync_path),
        "-vf", (
            f"scale={cw}:{ch}:flags=lanczos,"  # Lanczos補間で高品質
            "setsar=1,format=yuv420p"
        ),
        "-c:v", "libx264",
        "-crf", "16",
        "-preset", "fast",
        "-an",
        str(face_restored_path),
    ])

    # Step 6: 元動画にオーバーレイして完成 (音声付き)
    logger.info("Step6: 元動画にオーバーレイ + 音声合成 (CRF=%d)...", output_crf)
    run_ffmpeg([
        "-i", str(face_video),
        "-i", str(face_restored_path),
        "-i", str(audio),
        "-filter_complex",
        (
            f"[0:v][1:v]overlay={cx}:{cy}:shortest=1[outv];"
            "[2:a]aformat=sample_rates=44100:channel_layouts=stereo[outa]"
        ),
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-crf", str(output_crf),
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ])

    # クリーンアップ
    for p in [face_crop_path, face_lipsync_path, face_restored_path]:
        p.unlink(missing_ok=True)

    logger.info("=== 全身Wav2Lip完了 → %s ===", output)
    return True


def _lipsync_direct(
    face_video: Path,
    audio: Path,
    output: Path,
    vid_w: int,
    vid_h: int,
    lipsync_scale: int,
    output_crf: int,
) -> bool:
    """顔検出失敗時: Wav2Lip を動画全体に直接適用 (フォールバック)"""
    logger.info("フォールバック: Wav2Lip を動画全体に直接適用")

    # スケールダウン (Wav2Lipが処理できる解像度に)
    scale_h = int(lipsync_scale * vid_h / vid_w) if vid_w > 0 else lipsync_scale
    scale_h -= scale_h % 2
    resized_path = output.parent / f"_direct_resized_{output.stem}.mp4"

    run_ffmpeg([
        "-i", str(face_video),
        "-vf", f"scale={lipsync_scale}:{scale_h}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-an",
        str(resized_path),
    ])

    lipsync_path = output.parent / f"_direct_lipsync_{output.stem}.mp4"
    WAV2LIP_TEMP_DIR.mkdir(exist_ok=True)

    w2l_result = subprocess.run([
        sys.executable,
        str(WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path",   str(WAV2LIP_CHECKPOINT),
        "--face",              str(resized_path),
        "--audio",             str(audio),
        "--outfile",           str(lipsync_path),
        "--pads",   "0", "30", "0", "0",
        "--resize_factor",     "1",
        "--face_det_batch_size",  "16",
        "--wav2lip_batch_size",   "128",
        "--nosmooth",
    ], capture_output=True, text=True, cwd=str(WAV2LIP_DIR), timeout=600)

    if w2l_result.returncode != 0 or not lipsync_path.exists():
        resized_path.unlink(missing_ok=True)
        return False

    # 元のサイズに戻して音声を合成
    run_ffmpeg([
        "-i", str(lipsync_path),
        "-i", str(audio),
        "-vf", f"scale={vid_w}:{vid_h}:flags=lanczos,setsar=1,format=yuv420p",
        "-c:v", "libx264", "-crf", str(output_crf), "-preset", "medium",
        "-map", "0:v", "-map", "1:a",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ])

    for p in [resized_path, lipsync_path]:
        p.unlink(missing_ok=True)

    logger.info("フォールバック完了 → %s", output)
    return True


# ──────────────────────────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="高品質全身動画対応 Wav2Lip リップシンク v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--face",          required=True, help="入力動画パス")
    parser.add_argument("--audio",         required=True, help="音声 WAV ファイルパス")
    parser.add_argument("--outfile",       required=True, help="出力動画パス")
    parser.add_argument("--lipsync_scale", type=int,   default=720,  help="Wav2Lip処理幅 (px) [デフォルト: 720]")
    parser.add_argument("--padding_ratio", type=float, default=0.45, help="顔BBoxパディング比率 [デフォルト: 0.45]")
    parser.add_argument("--crf",           type=int,   default=18,   help="出力CRF値 [デフォルト: 18]")
    args = parser.parse_args()

    logger.info("wav2lip_fullbody.py v3.0 起動")
    logger.info("  使用チェックポイント: %s", WAV2LIP_CHECKPOINT.name)

    success = lipsync_fullbody(
        face_video=Path(args.face),
        audio=Path(args.audio),
        output=Path(args.outfile),
        lipsync_scale=args.lipsync_scale,
        padding_ratio=args.padding_ratio,
        output_crf=args.crf,
    )

    if not success:
        logger.error("リップシンク失敗: 元動画をそのまま使用してください")
        sys.exit(1)


if __name__ == "__main__":
    main()
