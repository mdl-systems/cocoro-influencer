#!/usr/bin/env python3
"""generate_wan_video.py: Wan2.1 I2Vによるローカル動画生成

Klingの代替として、cocoro-render-01のRTX PRO 6000 Blackwell (96GB VRAM) で
Wan2.1 Image-to-Video を実行するスタンドアロンスクリプト。

orchestrator.py からサブプロセスとして呼び出される。

【実行環境】
    /data/venv/wan2/bin/python  (torch + Wan2.1ネイティブAPI)

【使い方】
    /data/venv/wan2/bin/python generate_wan_video.py \\
        --image   /data/outputs/cocoro_customer/avatar_neutral_upper.png \\
        --prompt  "natural pose, looking at camera, modern office" \\
        --outfile /data/outputs/cocoro_customer/scene_000_wan.mp4 \\
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
    """Wan2.1 I2V 推論を実行して動画を生成する (ネイティブWan API使用)

    進捗はstdoutに以下の形式で出力（orchestratorがパース可能）：
        WAN_STEP: {step}/{total_steps}
        WAN_PHASE: {phase_name}
    """
    import sys
    sys.path.insert(0, "/data/models/Wan2.1/src")

    import imageio
    import numpy as np
    import torch
    from PIL import Image
    import wan
    from wan.configs import WAN_CONFIGS

    if not image_path.exists():
        raise FileNotFoundError(f"入力画像が見つかりません: {image_path}")

    print(f"WAN_PHASE: モデルロード中", flush=True)
    logger.info("Wan2.1 モデルロード中: %s", model_path)
    t0 = time.time()

    cfg = WAN_CONFIGS['i2v-14B']
    wan_i2v = wan.WanI2V(
        config=cfg,
        checkpoint_dir=model_path,
        device_id=0,
        rank=0,
        t5_cpu=True,      # T5をCPUに (VRAM節約)
        init_on_cpu=True,
    )
    logger.info("モデルロード完了 (%.1f秒)", time.time() - t0)
    print(f"WAN_PHASE: モデルロード完了 ({time.time()-t0:.0f}秒)", flush=True)

    # 入力画像
    image = Image.open(image_path).convert("RGB")

    logger.info(
        "推論開始: %dx%d frames=%d steps=%d prompt='%s'",
        width, height, num_frames, num_inference_steps, prompt[:60],
    )
    print(f"WAN_PHASE: 推論開始 steps={num_inference_steps}", flush=True)
    t1 = time.time()

    # ステップ毎コールバック (stdout に WAN_STEP: X/N 形式で出力)
    _step_counter = [0]
    def _step_callback(step: int, timestep: float, latents: object) -> None:  # noqa: ANN001
        _step_counter[0] += 1
        print(f"WAN_STEP: {_step_counter[0]}/{num_inference_steps}", flush=True)

    _generate_kwargs = dict(
        input_prompt=prompt,
        img=image,
        max_area=width * height,   # 480*832=399360
        frame_num=num_frames,
        shift=3.0,                 # 480P推奨値
        sample_solver='unipc',
        sampling_steps=num_inference_steps,
        guide_scale=guidance_scale,
        n_prompt=negative_prompt,
        seed=seed if seed is not None else -1,
        offload_model=True,        # Ollama等が27GB占有している場合のOOM対策
    )
    try:
        # callback引数でステップ毎進捗を stdout に出力
        video_tensor = wan_i2v.generate(**_generate_kwargs, callback=_step_callback)
    except TypeError:
        # Wan2.1 バージョンによっては callback 未対応 → なしで再試行
        logger.warning("wan_i2v.generate: callback未対応 → フォールバック（進捗なし）")
        print("WAN_PHASE: callback未対応 → 進捗表示なしで推論継続", flush=True)
        video_tensor = wan_i2v.generate(**_generate_kwargs)

    logger.info("推論完了 (%.1f秒)", time.time() - t1)
    print(f"WAN_PHASE: 推論完了 ({time.time()-t1:.0f}秒)", flush=True)

    # 動画保存: tensor [C,N,H,W] or [N,C,H,W] -> [N,H,W,C] uint8
    output_path.parent.mkdir(parents=True, exist_ok=True)
    t = video_tensor.cpu().float()
    if t.dim() == 4:
        if t.shape[0] == 3:          # [C, N, H, W]
            t = t.permute(1, 2, 3, 0)   # -> [N, H, W, C]
        elif t.shape[1] == 3:        # [N, C, H, W]
            t = t.permute(0, 2, 3, 1)   # -> [N, H, W, C]
    frames_np = ((t.numpy() + 1) / 2 * 255).clip(0, 255).astype(np.uint8)
    imageio.mimwrite(str(output_path), frames_np, fps=16, quality=8)
    logger.info("動画保存完了: %s", output_path)


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
