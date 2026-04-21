#!/usr/bin/env python3
"""generate_instantid_poses.py: InstantIDを使ってポーズ別アバター画像を自動生成

アバターアップロード後に自動トリガーされるスクリプト。
顔写真（＋任意で全身写真）から、orchestratorが使用する4種のポーズ画像を生成する。

【実行環境】
    /data/models/InstantID/venv にPyTorch+InstantID環境が入っている

【使い方】
    /data/models/InstantID/venv/bin/python \\
        /home/cocoro-influencer/scripts/generate_instantid_poses.py \\
        --customer_name cocoro_customer

【生成ファイル (orchestratorのPOSE_IMAGE_MAPと一致させること)】
    avatar_neutral_upper.png  → upper_body + neutral
    avatar_fullbody_ref_gen.png → full_body + neutral
    avatar_greeting_full.png  → full_body + greeting
    avatar_walking_full.png   → full_body + walk
"""

import argparse
import sys
import time
from pathlib import Path

# InstantID のパス設定 (cocoro-render-01)
INSTANTID_DIR = Path("/data/models/InstantID")
CONTROLNET_PATH = str(INSTANTID_DIR / "checkpoints/ControlNetModel")
IP_ADAPTER_PATH = str(INSTANTID_DIR / "checkpoints/ip-adapter.bin")
BASE_MODEL_PATH = "/data/models/RealVisXL_V4.0"
ANTELOPEV2_ROOT = "/data/models"   # antelopev2フォルダがここに入っている

# 生成パラメータ（顔の一致度を優先した設定）
GEN_PARAMS = {
    "controlnet_conditioning_scale": 0.8,   # 構造的一致度
    "ip_adapter_scale": 0.85,              # 顔の一致度 (0.6→0.85: 別人問題を修正)
    "num_inference_steps": 50,
    "guidance_scale": 5.5,                 # 若干下げてip_adapterを活かす
}

NEG_PROMPT = (
    "(worst quality, low quality, sketch, anime, manga, CGI), "
    "watermark, text, logo, getty images, istock, plastic skin, "
    "smooth skin, perfect skin, doll, fake, artificial, over-smooth, airbrush"
)

BASE_PROMPT = (
    "a beautiful woman, RAW photo, 8k uhd, {pose}, "
    "professional photography, cinematic lighting, "
    "highly detailed, sharp focus, photorealistic"
)

# ポーズ定義: (出力ファイル名, ポーズ説明, 全身写真を使うか)
POSES = [
    (
        "avatar_neutral_upper.png",
        "upper body portrait, looking at camera, slight smile, "
        "modern office background, professional attire",
        False,   # 顔写真ベース
    ),
    (
        "avatar_fullbody_ref_gen.png",
        "full body standing, white studio background, professional pose, "
        "showing full figure from head to toe, elegant posture",
        True,    # 全身写真ベース
    ),
    (
        "avatar_greeting_full.png",
        "waving hand enthusiastically, warm friendly smile, greeting gesture, "
        "full body visible, white background, dynamic yet elegant",
        True,
    ),
    (
        "avatar_walking_full.png",
        "walking forward confidently, natural dynamic movement, "
        "full body visible, slight side angle, urban background",
        True,
    ),
]


def log(msg: str) -> None:
    """フラッシュあり出力（pipedでもリアルタイム確認できる）"""
    print(msg, flush=True)


def load_models():
    """InsightFace + InstantID パイプラインをロードする"""
    import cv2
    import torch
    import numpy as np
    sys.path.insert(0, str(INSTANTID_DIR))
    from insightface.app import FaceAnalysis
    from diffusers.models import ControlNetModel
    from diffusers import DPMSolverMultistepScheduler
    from pipeline_stable_diffusion_xl_instantid import StableDiffusionXLInstantIDPipeline

    log("FaceAnalysis (antelopev2) をロード中...")
    app = FaceAnalysis(
        name="antelopev2",
        root=ANTELOPEV2_ROOT,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))

    log("ControlNet をロード中...")
    controlnet = ControlNetModel.from_pretrained(
        CONTROLNET_PATH, torch_dtype=torch.float16
    )

    log("RealVisXL ベースモデルをロード中...")
    pipe = StableDiffusionXLInstantIDPipeline.from_pretrained(
        BASE_MODEL_PATH,
        controlnet=controlnet,
        torch_dtype=torch.float16,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.cuda()
    pipe.load_ip_adapter_instantid(IP_ADAPTER_PATH)
    log("モデルロード完了")

    return app, pipe


def get_face_embeddings(app, image_path: Path):
    """顔写真から FaceAnalysis の埋め込みとキーポイント画像を取得する"""
    import cv2
    import torch
    import numpy as np
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    img_resize = img.resize((1024, 1024))
    img_cv = cv2.cvtColor(np.array(img_resize), cv2.COLOR_RGB2BGR)

    faces = app.get(img_cv)
    if not faces:
        raise RuntimeError(f"顔が検出できませんでした: {image_path}")

    # 最大面積の顔を選択
    face = sorted(
        faces,
        key=lambda x: (x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]),
    )[-1]

    face_emb = torch.tensor(face["embedding"]).unsqueeze(0)
    # キーポイント画像: 顔写真を 1024x1024 にリサイズしたものをそのまま使用
    kps_img = img_resize

    return face_emb, kps_img


def generate_pose(pipe, face_emb, kps_img, prompt: str, output_path: Path) -> None:
    """1ポーズの画像を生成して保存する"""
    t = time.time()
    log(f"生成中: {output_path.name} ...")
    image = pipe(
        prompt=prompt,
        negative_prompt=NEG_PROMPT,
        image_embeds=face_emb,
        image=kps_img,
        **GEN_PARAMS,
    ).images[0]
    image.save(str(output_path))
    log(f"  保存: {output_path.name} ({time.time() - t:.1f}秒)")


def main() -> None:
    parser = argparse.ArgumentParser(description="InstantIDポーズ別アバター画像生成")
    parser.add_argument("--customer_name", required=True, help="顧客名（出力ディレクトリ名）")
    args = parser.parse_args()

    output_dir = Path(f"/data/outputs/{args.customer_name}")
    face_image_path = output_dir / "avatar.png"
    fullbody_image_path = output_dir / "avatar_fullbody_ref.png"

    # 入力検証
    if not face_image_path.exists():
        log(f"ERROR: 顔写真が見つかりません: {face_image_path}", )
        sys.exit(1)

    has_fullbody = fullbody_image_path.exists()
    log(f"顧客名: {args.customer_name}")
    log(f"顔写真: {face_image_path}")
    log(f"全身写真: {fullbody_image_path if has_fullbody else '（なし → 顔写真ベースで代替）'}")
    log("")

    # モデルロード
    app, pipe = load_models()

    # 顔写真からembeddings取得
    log("顔写真から埋め込み抽出中...")
    face_emb, face_kps = get_face_embeddings(app, face_image_path)

    # 全身写真からembeddings取得（ある場合）
    if has_fullbody:
        log("全身写真から埋め込み抽出中...")
        fb_emb, fb_kps = get_face_embeddings(app, fullbody_image_path)
    else:
        # 全身写真がない場合は顔写真ベースで代替
        fb_emb, fb_kps = face_emb, face_kps
        log("全身写真なし → 顔写真ベースで全身ポーズ生成")

    log("")
    total_start = time.time()

    # 各ポーズを生成
    for out_fname, pose_desc, use_fullbody in POSES:
        prompt = BASE_PROMPT.format(pose=pose_desc)
        emb = fb_emb if use_fullbody else face_emb
        kps = fb_kps if use_fullbody else face_kps
        out_path = output_dir / out_fname
        generate_pose(pipe, emb, kps, prompt, out_path)

    log("")
    log(f"✅ 全ポーズ生成完了 ({time.time() - total_start:.1f}秒) → {output_dir}")


if __name__ == "__main__":
    main()
