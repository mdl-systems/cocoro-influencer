#!/usr/bin/env python3
"""generate_wan_video.py: Wan2.1 I2Vによるローカル動画生成

Klingの代替として、cocoro-render-01のRTX PRO 6000 Blackwell (96GB VRAM) で
Wan2.1 Image-to-Video を実行するスタンドアロンスクリプト。

orchestrator.py からサブプロセスとして呼び出される。

【実行環境】
    /data/venv/wan2/bin/python  (torch + diffusers + Wan2.1対応)

【使い方】
    /data/venv/wan2/bin/python generate_wan_video.py \\
        --image   /mnt/data/outputs/cocoro_customer/avatar_neutral_upper.png \\
        --prompt  "natural pose, looking at camera, modern office" \\
        --outfile /mnt/data/outputs/cocoro_customer/scene_000_kling.mp4 \\
        --num_frames 97  \\
        --steps 30

【生成仕様】
    デフォルト: 480p (832x480 or 480x832) 97フレーム @24fps ≒ 4秒
    9:16 縦動画: 480x832
"""

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def save_frames_to_video(frames: list, output_path: Path, fps: int = 24) -> None:
    """PIL フレームリストを MP4 として保存する（ffmpeg-python 不使用・subprocess 使用）"""
    import subprocess
    import tempfile

    import numpy as np

    tmp_dir = Path(tempfile.mkdtemp(prefix="wan2_frames_"))
    try:
        for i, frame in enumerate(frames):
            frame.save(tmp_dir / f"frame_{i:06d}.png")

        cmd = [
            "ffmpeg",
            "-framerate", str(fps),
            "-i", str(tmp_dir / "frame_%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-movflags", "+faststart",
            str(output_path), "-y",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg失敗: {result.stderr[-500:]}")
        logger.info("動画保存完了: %s", output_path)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def generate(
    image_path: Path,
    prompt: str,
    output_path: Path,
    model_path: str,
    negative_prompt: str,
    num_frames: int,
    num_inference_steps: int,
    guidance_scale: float,
    width: int,
    height: int,
    seed: int | None,
) -> None:
    """Wan2.1 I2V 推論を実行して動画を生成する"""
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
    from PIL import Image

    if not image_path.exists():
        raise FileNotFoundError(f"入力画像が見つかりません: {image_path}")

    logger.info("Wan2.1 モデルロード中: %s", model_path)
    t0 = time.time()

    # VAE (bf16推奨)
    vae = AutoencoderKLWan.from_pretrained(
        model_path,
        subfolder="vae",
        torch_dtype=torch.float32,
    )

    # パイプライン (bf16 = Blackwell最適)
    dtype = torch.bfloat16  # RTX PRO 6000 Blackwell は bf16 サポート
    pipe = WanImageToVideoPipeline.from_pretrained(
        model_path,
        vae=vae,
        torch_dtype=dtype,
    )
    pipe.to("cuda")
    pipe.enable_model_cpu_offload()  # VRAM節約（96GBあるが念のため）

    logger.info("モデルロード完了 (%.1f秒)", time.time() - t0)

    # 入力画像
    image = Image.open(image_path).convert("RGB")
    image = image.resize((width, height))

    # シード固定
    generator = None
    if seed is not None:
        generator = torch.Generator(device="cuda").manual_seed(seed)
        logger.info("シード固定: %d", seed)

    logger.info(
        "推論開始: %dx%d frames=%d steps=%d prompt='%s'",
        width, height, num_frames, num_inference_steps, prompt[:60],
    )
    t1 = time.time()

    with torch.no_grad():
        output = pipe(
            image=image,
            prompt=prompt,
            negative_prompt=negative_prompt,
            height=height,
            width=width,
            num_frames=num_frames,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )

    logger.info("推論完了 (%.1f秒)", time.time() - t1)

    frames = output.frames[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_frames_to_video(frames, output_path, fps=16)  # Wan2.1は16fps出力


def main() -> None:
    parser = argparse.ArgumentParser(description="Wan2.1 I2V ローカル動画生成")
    parser.add_argument("--image",    required=True,  help="入力画像パス")
    parser.add_argument("--prompt",   required=True,  help="動画生成プロンプト")
    parser.add_argument("--outfile",  required=True,  help="出力MP4パス")
    parser.add_argument("--model",    default="/data/models/Wan2.1/I2V-14B-480P",
                        help="Wan2.1ローカルモデルパス")
    parser.add_argument("--neg_prompt", default=(
        "Bright tones, overexposed, static, blurred details, subtitles, "
        "style, works, paintings, images, static, overall gray, worst quality, "
        "low quality, JPEG compression residual, ugly, incomplete, extra fingers, "
        "poorly drawn hands, poorly drawn faces, deformed, disfigured, "
        "misshapen limbs, fused fingers, still picture, messy background, "
        "three legs, many people in the picture, watermark"
    ))
    parser.add_argument("--num_frames",  type=int,   default=97,
                        help="生成フレーム数 (97≒4秒@16fps, 193≒8秒)")
    parser.add_argument("--steps",       type=int,   default=30,
                        help="推論ステップ数")
    parser.add_argument("--guidance",    type=float, default=5.0,
                        help="ガイダンススケール")
    parser.add_argument("--width",       type=int,   default=480,
                        help="出力幅 (縦動画は480)")
    parser.add_argument("--height",      type=int,   default=832,
                        help="出力高さ (縦動画は832 = 480x832で9:16)")
    parser.add_argument("--seed",        type=int,   default=None,
                        help="ランダムシード")
    args = parser.parse_args()

    t_total = time.time()
    generate(
        image_path=Path(args.image),
        prompt=args.prompt,
        output_path=Path(args.outfile),
        model_path=args.model,
        negative_prompt=args.neg_prompt,
        num_frames=args.num_frames,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        width=args.width,
        height=args.height,
        seed=args.seed,
    )
    logger.info("✅ 完了 (総計%.1f秒)", time.time() - t_total)


if __name__ == "__main__":
    main()
