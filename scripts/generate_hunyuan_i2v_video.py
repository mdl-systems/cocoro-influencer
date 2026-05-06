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
    parser.add_argument("--guidance_scale", type=float, default=6.0, help="ガイダンス強度（高いほど動きが大きい）")
    parser.add_argument("--seed",         type=int, default=42,   help="乱数シード")
    parser.add_argument("--cpu_offload",  action="store_true", default=True,
                        help="CPU オフロード有効（VRAM 節約）")
    return parser.parse_args()


def build_motion_prompt(base_prompt: str) -> str:
    """プロンプトに動き・品質タグを追加"""
    motion_tags = (
        "natural body movement, subtle arm gestures, "
        "head nodding, expressive facial expressions, "
        "talking to camera"
    )
    quality_tags = (
        "photorealistic, high quality, 4k, "
        "professional lighting, sharp focus"
    )
    return f"{base_prompt}, {motion_tags}, {quality_tags}"


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

    if args.cpu_offload:
        pipe.enable_model_cpu_offload()
        print("[HunyuanI2V] CPU オフロード有効", flush=True)
    else:
        pipe.to("cuda")

    # ────────────────────────────────
    # 推論
    # ────────────────────────────────
    prompt = build_motion_prompt(args.prompt)
    print(f"[HunyuanI2V] プロンプト: {prompt[:80]}...", flush=True)

    image = load_image(args.image)
    generator = torch.Generator("cpu").manual_seed(args.seed)

    print(f"[HunyuanI2V] 推論開始 (steps={args.steps}, guidance={args.guidance_scale})", flush=True)
    output = pipe(
        image=image,
        prompt=prompt,
        height=args.height,
        width=args.width,
        num_frames=args.num_frames,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance_scale,
        generator=generator,
    ).frames[0]

    # ────────────────────────────────
    # 保存
    # ────────────────────────────────
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    export_to_video(output, args.output, fps=args.fps)

    elapsed = time.time() - t_start
    print(f"[HunyuanI2V] 完了: {args.output} ({elapsed:.1f}秒)", flush=True)


if __name__ == "__main__":
    main()
