#!/usr/bin/env python3
"""
MuseTalk リップシンク生成スクリプト
musetalk conda env の python で実行される
orchestrator.py からサブプロセスとして呼び出される

使用例:
    /data/miniconda/bin/conda run -n musetalk python generate_musetalk_lipsync.py \
        --video /data/outputs/test/scene_000_clip.mp4 \
        --audio /data/outputs/test/scene_000_voice.wav \
        --output /data/outputs/test/scene_000_lipsync.mp4
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_MUSETALK_DIR = "/data/models/MuseTalk"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MuseTalk リップシンク生成")
    parser.add_argument("--video",        required=True, help="入力動画パス（HunyuanVideo生成クリップ）")
    parser.add_argument("--audio",        required=True, help="入力音声パス（TTSフルオーディオ）")
    parser.add_argument("--output",       required=True, help="出力MP4パス（リップシンク済み）")
    parser.add_argument("--musetalk_dir", default=DEFAULT_MUSETALK_DIR, help="MuseTalkリポジトリディレクトリ")
    parser.add_argument("--fps",          type=int, default=15,  help="出力FPS")
    parser.add_argument("--batch_size",   type=int, default=8,   help="推論バッチサイズ")
    parser.add_argument("--bbox_shift",   type=int, default=0,   help="顔バウンディングボックスシフト量")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    musetalk_dir = Path(args.musetalk_dir)

    video_path = Path(args.video).resolve()
    audio_path = Path(args.audio).resolve()
    output_path = Path(args.output)

    if not video_path.exists():
        print(f"[MuseTalk] エラー: 入力動画が見つかりません: {video_path}", flush=True)
        sys.exit(1)
    if not audio_path.exists():
        print(f"[MuseTalk] エラー: 入力音声が見つかりません: {audio_path}", flush=True)
        sys.exit(1)

    # YAML config を一時ファイルに書き出し
    config_file = Path(tempfile.mktemp(suffix=".yaml"))
    config_file.write_text(
        f'task_0:\n'
        f'  video_path: "{video_path}"\n'
        f'  audio_path: "{audio_path}"\n'
    )

    out_dir = Path(tempfile.mkdtemp(prefix="musetalk_out_"))

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(musetalk_dir)

        cmd = [
            sys.executable,
            "-W", "ignore",
            str(musetalk_dir / "scripts" / "inference.py"),
            "--inference_config", str(config_file),
            "--unet_config",      str(musetalk_dir / "models/musetalkV15/musetalk.json"),
            "--unet_model_path",  str(musetalk_dir / "models/musetalkV15/unet.pth"),
            "--result_dir",       str(out_dir),
            "--fps",              str(args.fps),
            "--batch_size",       str(args.batch_size),
            "--bbox_shift",       str(args.bbox_shift),
        ]

        print(
            f"[MuseTalk] 推論開始 video={video_path.name} audio={audio_path.name}",
            flush=True,
        )

        result = subprocess.run(
            cmd,
            cwd=str(musetalk_dir),
            env=env,
            timeout=900,
        )

        if result.returncode != 0:
            print(f"[MuseTalk] 推論失敗 (returncode={result.returncode})", flush=True)
            sys.exit(1)

        # 出力MP4を探す（temp_ で始まらない、最新の mp4）
        mp4_files = sorted(
            out_dir.rglob("*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        final_files = [f for f in mp4_files if not f.name.startswith("temp_")]
        if not final_files:
            final_files = mp4_files
        if not final_files:
            print("[MuseTalk] エラー: 出力ファイルが見つかりません", flush=True)
            sys.exit(1)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(final_files[0]), str(output_path))
        print(f"[MuseTalk] 完了: {output_path}", flush=True)

    finally:
        config_file.unlink(missing_ok=True)
        shutil.rmtree(str(out_dir), ignore_errors=True)


if __name__ == "__main__":
    main()
