#!/usr/bin/env python3
"""
HunyuanVideo-I2V 動画生成スクリプト
orchestrator.py からサブプロセスとして呼び出される
"""
import argparse
import sys
import time
import torch
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="HunyuanVideo-I2V 動画生成")
    parser.add_argument("--image",        required=True,  help="入力画像パス")
    parser.add_argument("--prompt",       required=True,  help="動画生成プロンプト")
    parser.add_argument("--output",       required=True,  help="出力MP4パス")
    parser.add_argument("--model_dir",    default="/data/models/HunyuanVideo-I2V", help="モデルディレクトリ")
    parser.add_argument("--height",       type=int, default=832,  help="動画の高さ（縦長推奨）")
    parser.add_argument("--width",        type=int, default=480,  help="動画の幅")
    parser.add_argument("--num_frames",   type=int, default=61,   help="フレーム数（4n+1）")
    parser.add_argument("--steps",        type=int, default=30,   help="推論ステップ数")
    parser.add_argument("--fps",          type=int, default=15,   help="出力 FPS")
    parser.add_argument("--guidance_scale", type=float, default=9.0,
                        help="ガイダンス強度（9.0推奨: フレームアウト・ボケ防止）")
    parser.add_argument("--seed",         type=int, default=42,   help="乱数シード")
    parser.add_argument("--cpu_offload",  action="store_true", default=True,
                        help="CPU オフロード有効（VRAM 節約）")
    return parser.parse_args()


def build_motion_prompt(base_prompt: str) -> str:
    """プロンプトに動き・品質タグを追加"""
    motion_tags = (
        "minimal subtle movement, slight head nod, "
        "gentle natural gestures, stays centered in frame, "
        "upper body always visible, face always in frame"
    )
    quality_tags = (
        "photorealistic, high quality, 4k, sharp focus, "
        "in focus throughout, professional studio lighting, "
        "consistent face, no blur, crisp details, stable"
    )
    return f"{base_prompt}, {motion_tags}, {quality_tags}"


NEGATIVE_PROMPT = (
    "out of frame, cropped face, extreme movement, "
    "camera shake, motion blur, defocus blur, "
    "blurry, low quality, distortion, "
    "person leaving frame, off-center"
)


def main():
    args = parse_args()
    t_start = time.time()

    print(f"[HunyuanI2V] 開始: image={args.image}", flush=True)
    print(f"[HunyuanI2V] 解像度: {args.width}x{args.height} frames={args.num_frames}", flush=True)

    # ────────────────────────────────
    # モデルロード
    # ────────────────────────────────
    from diffusers import HunyuanVideoImageToVideoPipeline, HunyuanVideoTransformer3DModel
    from diffusers.utils import load_image, export_to_video

    model_dir = args.model_dir
    print(f"[HunyuanI2V] Transformer ロード中: {model_dir}", flush=True)

    transformer = HunyuanVideoTransformer3DModel.from_pretrained(
        model_dir,
        subfolder="transformer",
        torch_dtype=torch.bfloat16,
    )

    print("[HunyuanI2V] Pipeline ロード中...", flush=True)
    pipe = HunyuanVideoImageToVideoPipeline.from_pretrained(
        model_dir,
        transformer=transformer,
        torch_dtype=torch.float16,
    )
    pipe.vae.enable_tiling()
    pipe.vae.enable_slicing()  # VAEアーティファクト軽減・ピンボケ防止

    if args.cpu_offload:
        pipe.enable_model_cpu_offload()
        print("[HunyuanI2V] CPU オフロード有効", flush=True)
    else:
        pipe.to("cuda")

    # フレーム数を 41 に制限（短くするほどフレームアウト防止）
    num_frames = min(args.num_frames, 41)
    if num_frames != args.num_frames:
        print(f"[HunyuanI2V] フレーム数を {args.num_frames} → {num_frames} に制限 (ピンボケ・フレームアウト防止)", flush=True)

    # ────────────────────────────────
    # 推論
    # ────────────────────────────────
    prompt = build_motion_prompt(args.prompt)
    print(f"[HunyuanI2V] プロンプト: {prompt[:80]}...", flush=True)

    image = load_image(args.image)
    generator = torch.Generator("cpu").manual_seed(args.seed)

    print(f"[HunyuanI2V] 推論開始 (steps={args.steps}, guidance={args.guidance_scale}, frames={num_frames})", flush=True)
    output = pipe(
        image=image,
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        height=args.height,
        width=args.width,
        num_frames=num_frames,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance_scale,
        generator=generator,
    ).frames[0]

    # ────────────────────────────────
    # 保存 + FFmpeg シャープニング後処理
    # ────────────────────────────────
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # 一時ファイルに出力してからシャープニング
    import subprocess as _sp
    tmp_raw = args.output + ".raw.mp4"
    export_to_video(output, tmp_raw, fps=args.fps)

    # FFmpeg unsharp フィルターで動きボケを軽減
    # unsharp=luma_msize_x:luma_msize_y:luma_amount (5:5:1.5 = 強め, 3:3:0.8 = 弱め)
    sharp_cmd = [
        "ffmpeg", "-y",
        "-i", tmp_raw,
        "-vf", "unsharp=5:5:1.2:5:5:0.0",   # 輝度シャープニング強度 1.2
        "-c:v", "libx264", "-crf", "18",       # 高品質エンコード
        "-preset", "fast",
        "-c:a", "copy",
        args.output,
    ]
    result = _sp.run(sharp_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # シャープニング失敗時はそのままコピー
        import shutil
        shutil.move(tmp_raw, args.output)
        print(f"[HunyuanI2V] シャープニングスキップ（ffmpegエラー）: {result.stderr[:200]}", flush=True)
    else:
        Path(tmp_raw).unlink(missing_ok=True)
        print(f"[HunyuanI2V] シャープニング適用完了 (unsharp 1.2)", flush=True)

    elapsed = time.time() - t_start
    print(f"[HunyuanI2V] 完了: {args.output} ({elapsed:.1f}秒)", flush=True)


if __name__ == "__main__":
    main()
